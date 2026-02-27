import logging
from typing import Optional, List, Dict, Any

from langfuse import observe

from app.agents.base import BaseAgent
from app.schemas.agent_state import EvaluatorState
from app.schemas.agent_output import EvaluatorOutput, ConceptDelta
from app.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


EVALUATOR_SYSTEM_PROMPT = """You are the **Evaluator** in an adaptive tutoring system.
Assess the student's latest message in the context of the tutoring conversation.

# What you receive
- The tutor's previous response and any question it contained.
- The student's reply.
- The focus concepts, current mastery levels, and effective step type for this turn.
- If no explicit question was asked, evaluate what the student's message reveals about their understanding of the focus concepts.

# Scoring
- `overall_score` (0.0–1.0): 0.0 = wrong/off-topic, 0.3 = some awareness, 0.5 = partial, 0.7 = mostly correct, 0.9 = excellent, 1.0 = perfect.
- `correctness_label`: "correct" (≥0.8), "partial" (0.4–0.8), "incorrect" (<0.4), "unclear" (off-topic/unintelligible).

# Concept deltas
For each focus concept provide an entry in `concept_deltas`:
```json
{ "<concept_name>": { "score": 0.0-1.0, "delta": -0.3 to 0.3, "weight": 0.3-1.0, "role": "primary"|"support"|"prereq" } }
```
- `delta` > 0 if student showed understanding, < 0 if misconception revealed.
- `weight`: 1.0 for primary, 0.6 for support, 0.3 for prereq.

# Other fields
- `overall_feedback`: 1–2 sentence constructive feedback.
- `misconceptions`: list of specific misconceptions (empty list if none).
- `confidence`: confidence in this evaluation (0.0-1.0).
- `uncertainty`: uncertainty estimate for this evaluation (0.0-1.0).
- `uncertainty_hints`: short machine-readable hints explaining uncertainty.
- `ready_to_advance`: true only if student is ready to progress to next step/objective.
- `recommended_intervention`: one of `reteach|worked_example|guided_practice|quick_check|advance`.

Output valid JSON only."""


class EvaluatorAgent(BaseAgent[EvaluatorState, EvaluatorOutput]):
    """Evaluator agent that assesses student responses."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        super().__init__("Evaluator")
        self.llm = llm_provider

    @property
    def system_prompt(self) -> str:
        return EVALUATOR_SYSTEM_PROMPT

    @observe(name="agent.evaluator", capture_input=False)
    async def run(self, state: EvaluatorState) -> EvaluatorOutput:
        logger.info(f"EvaluatorAgent: concepts={state.focus_concepts[:3]}, msg={state.student_message[:50]}...")

        if self.llm:
            try:
                return await self.llm.generate_json(
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": self._build_prompt(state)},
                    ],
                    schema=EvaluatorOutput,
                    max_tokens=1024,
                    trace_name="agent.evaluator.assess",
                    trace_metadata={
                        "focus_concepts": state.focus_concepts[:5],
                        "has_tutor_question": state.tutor_question is not None,
                        "effective_step_type": state.effective_step_type or state.current_step,
                    },
                )
            except Exception as e:
                logger.warning(f"LLM evaluation failed: {e}, using fallback")

        return self._fallback_evaluation(state)

    def _build_prompt(self, state: EvaluatorState) -> str:
        obj = state.current_objective
        scope = state.concept_scope

        obj_block = (
            f"OBJECTIVE: {obj.get('title', 'N/A')}\n"
            f"  Primary concepts: {scope.get('primary', [])}\n"
            f"  Support concepts: {scope.get('support', [])}\n"
            f"  Canonical step: {state.current_step or 'N/A'}\n"
            f"  Effective step: {state.effective_step_type or state.current_step or 'N/A'}"
        )

        # Tutor context
        tutor_ctx = ""
        if state.tutor_response:
            tutor_ctx = f"\nTUTOR'S PREVIOUS RESPONSE:\n{state.tutor_response[:600]}\n"

        question_line = ""
        if state.tutor_question:
            question_line = f'\nQUESTION THE STUDENT IS ANSWERING: "{state.tutor_question}"'
        else:
            question_line = "\nNO EXPLICIT QUESTION — evaluate what the student's message reveals about their understanding."

        mastery_lines = [f"  {c}: {v:.2f}" for c, v in state.mastery_snapshot.items()]
        mastery_block = "CURRENT MASTERY:\n" + "\n".join(mastery_lines) if mastery_lines else "CURRENT MASTERY: (new student)"

        return f"""{obj_block}
{tutor_ctx}{question_line}

STUDENT'S MESSAGE: "{state.student_message}"

FOCUS CONCEPTS: {state.focus_concepts}

{mastery_block}

Evaluate the student's response. Return JSON with overall_score, correctness_label, overall_feedback, misconceptions, concept_deltas, confidence, uncertainty, uncertainty_hints, ready_to_advance, and recommended_intervention."""

    async def evaluate(self, state: EvaluatorState) -> EvaluatorOutput:
        return await self.run(state)

    def _fallback_evaluation(self, state: EvaluatorState) -> EvaluatorOutput:
        message = (state.student_message or "").lower()
        primary = set(state.concept_scope.get("primary", []))
        prereq = set(state.concept_scope.get("prereq", []))
        uncertainty_hints: list[str] = []

        def _concept_mentioned(concept: str) -> bool:
            token = concept.replace("_", " ").lower()
            return token in message

        confusion_terms = ("confused", "don't get", "dont get", "stuck", "not sure")
        has_confusion_signal = any(term in message for term in confusion_terms)
        if has_confusion_signal:
            uncertainty_hints.append("student_confusion_signal")

        if not state.focus_concepts:
            uncertainty_hints.append("no_focus_concepts")

        concept_deltas = {}
        concept_scores: list[float] = []
        for concept in state.focus_concepts:
            if concept in primary:
                role = "primary"
                base_weight = 1.0
            elif concept in prereq:
                role = "prereq"
                base_weight = 0.5
            else:
                role = "support"
                base_weight = 0.6

            mentioned = _concept_mentioned(concept)
            concept_score = 0.75 if mentioned else 0.35
            if has_confusion_signal:
                concept_score -= 0.2
            concept_score = max(0.0, min(1.0, concept_score))
            concept_scores.append(concept_score)

            if concept_score >= 0.8:
                delta_val = 0.18
            elif concept_score >= 0.55:
                delta_val = 0.08
            elif concept_score >= 0.4:
                delta_val = 0.02
            else:
                delta_val = -0.06 if role == "primary" else -0.03

            concept_deltas[concept] = ConceptDelta(
                score=concept_score,
                delta=delta_val,
                weight=base_weight,
                role=role,
            )

        overall_score = (
            sum(concept_scores) / len(concept_scores)
            if concept_scores
            else (0.25 if has_confusion_signal else 0.4)
        )
        if overall_score >= 0.8:
            label = "correct"
            feedback = "Good explanation. Keep using this same reasoning pattern."
            ready_to_advance = True
            recommended_intervention = "advance"
        elif overall_score >= 0.4:
            label = "partial"
            feedback = "Good progress. Tighten your explanation around the main concept link."
            ready_to_advance = False
            recommended_intervention = "guided_practice"
        elif overall_score >= 0.2:
            label = "incorrect"
            feedback = "You're close, but the core concept link is off. Let's rebuild it step by step."
            ready_to_advance = False
            recommended_intervention = "worked_example"
        else:
            label = "unclear"
            feedback = "I could not infer your understanding clearly. Please explain your reasoning more explicitly."
            ready_to_advance = False
            recommended_intervention = "reteach"

        mentioned_any = any(_concept_mentioned(c) for c in state.focus_concepts)
        if not mentioned_any and state.focus_concepts:
            uncertainty_hints.append("no_focus_concept_overlap")

        if len(state.student_message.split()) < 5:
            uncertainty_hints.append("very_short_response")

        confidence = 0.75 if mentioned_any and not has_confusion_signal else 0.5
        confidence = max(0.2, min(0.95, confidence))
        uncertainty = round(1.0 - confidence, 3)

        misconceptions = []
        missing_primary = [c for c in primary if not _concept_mentioned(c)]
        if missing_primary:
            misconceptions.append(f"missing_primary_concepts:{','.join(sorted(missing_primary))}")
        if has_confusion_signal:
            misconceptions.append("self_reported_confusion")

        return EvaluatorOutput(
            overall_score=overall_score,
            correctness_label=label,
            multi_concept=len(state.focus_concepts) > 1,
            overall_feedback=feedback,
            misconceptions=misconceptions,
            concept_deltas=concept_deltas if concept_deltas else None,
            confidence=confidence,
            uncertainty=uncertainty,
            uncertainty_hints=uncertainty_hints,
            ready_to_advance=ready_to_advance,
            recommended_intervention=recommended_intervention,
        )
