import logging
from typing import Optional

from langfuse import observe

from app.agents.base import BaseAgent
from app.schemas.agent_state import PolicyState
from app.schemas.agent_output import (
    PolicyOrchestratorOutput,
    PedagogicalAction,
    ProgressionDecision,
)
from app.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


POLICY_SYSTEM_PROMPT = """You are the **Policy Orchestrator** of an agentic tutoring system.
Your job is to decide *what should happen this turn* so the other agents (Tutor, Evaluator) can act on your decision.

# Architecture
The session is organised into **learning objectives** (sequential flow).
Each objective has a **step roadmap** — a suggested pedagogical path.
You are the PRIMARY decision-maker for progression.

**Important — Fluid Progression Philosophy:**
- The step roadmap is a SUGGESTED PATH, not a rigid constraint. It provides pedagogical structure and guides retrieval, but you decide the pace.
- Success criteria (min_mastery, min_correct) are REFERENCE GUIDELINES that inform your judgment. They do NOT hard-block your decisions. The system will trust your call.
- Focus on the student's DEMONSTRATED UNDERSTANDING. If they clearly get the material, advance confidently — even if formal metrics haven't caught up. If they're struggling, stay and support them.
- Be natural and adaptive. A good tutor doesn't mechanically follow a checklist — they read the room.
- Avoid unnecessarily lingering on a step the student has already grasped. Equally, don't rush past confusion.

# Your Decisions

## pedagogical_action (what the tutor should do)
- introduce: First exposure to a concept — define it, motivate it.
- explain: Deeper elaboration, worked examples, connections.
- example: Provide a concrete worked example.
- hint: Give a nudge without revealing the answer.
- question: Ask the student a targeted Socratic question to check understanding.
- assess: Pose a problem for the student to solve independently.
- correct: Address a misconception the student just revealed.
- clarify: Re-explain something the student found confusing.
- summarize: Recap key points before moving on.
- motivate: Encourage the student or connect to real-world relevance.

## progression_decision (how to move through the step roadmap)
- 1 (CONTINUE_STEP): Stay on current step.
- 2 (ADVANCE_STEP): Move to the next step in the roadmap.
- 3 (SKIP_TO_STEP): Jump forward to a later roadmap step.
- 4 (INSERT_AD_HOC): Stay on current step but insert a one-turn ad-hoc move.
- 5 (ADVANCE_OBJECTIVE): Move to the next objective (student has demonstrated sufficient understanding).
- 6 (END_SESSION): The student has completed all objectives or explicitly wants to stop.

# Decision Guidelines
- ADVANCE_STEP when you judge the current step goal is met based on the student's responses.
- Use CONTINUE_STEP/INSERT_AD_HOC when the student needs more support — struggling, gave a partial answer, or you want to ask a Socratic follow-up. But be aware of ad-hoc budget — after the limit, you MUST advance.
- ADVANCE_OBJECTIVE when the student has shown solid understanding of the primary concepts. Use success criteria as a reference point (mastery ≥ 0.7 is a good signal), but trust your holistic assessment of the conversation.
- If evaluation shows score ≥ 0.8 on an assess step, lean toward ADVANCE_STEP.
- If evaluation shows score < 0.4, use CONTINUE_STEP (or INSERT_AD_HOC) and set action to hint or correct.
- **Reconnection rule**: If ad_hoc_count is approaching max_ad_hoc_per_objective, you should ADVANCE_STEP to reconnect with the roadmap.
- SKIP_TO_STEP is forward-only and must target a valid, skippable step window.
- Always provide clear `reasoning` explaining your decision.
- Set `target_concepts` to the 1-3 concepts the tutor should focus on this turn.
- Set `planner_guidance` with a short instruction for the tutor (e.g., "Ask a Socratic question about finite additivity" or "Scaffold with a worked example before assessing").
- Set `student_intent` to one of: engaged, confused, bored, move_on, asking_question, answer_attempt, off_topic, frustrated.

## recommended_strategy (which teaching approach the tutor should use)
- **direct**: Best for *motivate* and *define* steps, or when introducing a brand-new concept. Also good after incorrect answers to re-teach clearly.
- **socratic**: Best for *explain* and *practice* when mastery is 0.2–0.6. Probes the student's reasoning to deepen understanding.
- **scaffolded**: Best when student is struggling (eval score < 0.5 or mastery < 0.3). Break the problem into sub-steps, provide partial solutions.
- **assessment**: Best for *assess* steps. Pose a problem and let the student work independently.
- **review**: Best for *summarize* steps or before advancing to a new objective. Summarise and consolidate.

Choose the strategy that matches the step type and the student's current level. For example:
- motivate/define step → "direct"
- explain step with low mastery → "scaffolded"
- explain step with medium mastery → "socratic"
- practice step → "socratic" or "scaffolded" depending on student level
- assess step → "assessment"
- after incorrect answer → "scaffolded" or "direct"

## retrieval_directives (optional — guides what content to retrieve)
Provide a `retrieval_directives` object to steer knowledge retrieval for this turn.
- `query`: A short, specific natural-language query describing the content the tutor needs (e.g., "definition and properties of sigma-algebras", "worked example of Bayes' theorem application"). Do NOT repeat the student's message verbatim — describe the information the tutor should retrieve from the resource.
- `focus`: One of "primary", "prereq", "example", "misconception" to prioritise a category of evidence.
- `expand_prereqs`: Boolean (true if the tutor should also pull prerequisite material).

Example:
```json
"retrieval_directives": {
    "query": "definition and key properties of conditional expectation",
    "focus": "primary",
    "expand_prereqs": false
}
```

Output valid JSON matching the schema."""


class PolicyAgent(BaseAgent[PolicyState, PolicyOrchestratorOutput]):
    """Policy agent that orchestrates the tutoring workflow."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        super().__init__("PolicyOrchestrator")
        self.llm = llm_provider

    @property
    def system_prompt(self) -> str:
        return POLICY_SYSTEM_PROMPT

    @observe(name="agent.policy", capture_input=False)
    async def run(self, state: PolicyState) -> PolicyOrchestratorOutput:
        logger.info(f"PolicyAgent: step={state.current_step}, msg={state.student_message[:50]}...")

        if self.llm:
            try:
                result = await self.llm.generate_json(
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": self._build_prompt(state)},
                    ],
                    schema=PolicyOrchestratorOutput,
                    max_tokens=800,
                    trace_name="agent.policy.decide",
                    trace_metadata={
                        "step_type": state.current_step,
                        "step_index": getattr(state, "current_step_index", 0),
                    },
                )
                return self._apply_decision_guards(state, result)
            except Exception as e:
                logger.warning(f"LLM policy failed: {e}, using fallback")

        return self._apply_decision_guards(state, self._fallback_policy(state))

    def _build_prompt(self, state: PolicyState) -> str:
        cs = state.curriculum_slice
        obj = cs.get("current_objective", {})
        current_step = cs.get("current_step")
        lookahead = cs.get("lookahead_steps", [])
        scope = obj.get("concept_scope", {})
        step_index = getattr(state, "current_step_index", 0)
        ad_hoc_count = getattr(state, "ad_hoc_count", 0)
        max_ad_hoc = getattr(state, "max_ad_hoc_per_objective", 3)

        # Session journey context
        journey_lines = []
        for oq in state.objective_queue_summary:
            marker = "→" if oq.get("is_current") else ("✓" if oq.get("is_completed") else " ")
            journey_lines.append(f"  {marker} {oq.get('id','?')}: {oq.get('title','?')} [{', '.join(oq.get('primary_concepts', []))}]")
        journey_block = (
            f"SESSION PROGRESS: Objective {state.current_objective_index + 1}/{state.total_objectives}\n"
            + "\n".join(journey_lines)
        ) if journey_lines else ""

        # Objective context
        roadmap = obj.get("step_roadmap") or []
        total_steps = len(roadmap) if isinstance(roadmap, list) else "?"
        obj_block = (
            f"CURRENT OBJECTIVE [{step_index + 1}/{total_steps} steps]\n"
            f"  Title: {obj.get('title', 'N/A')}\n"
            f"  Description: {obj.get('description', 'N/A')}\n"
            f"  Primary concepts: {scope.get('primary', [])}\n"
            f"  Support concepts: {scope.get('support', [])}\n"
            f"  Success criteria: {obj.get('success_criteria', {})}"
        )

        # Current step
        step_block = (
            f"CURRENT STEP: {current_step.get('type', 'N/A')}\n"
            f"  Target concepts: {current_step.get('target_concepts', [])}\n"
            f"  Goal: {current_step.get('goal', 'N/A')}"
        )

        # Intermediate step tracking
        intermediate_block = (
            f"AD-HOC STEPS: {ad_hoc_count}/{max_ad_hoc} "
            f"({'MUST advance soon' if ad_hoc_count >= max_ad_hoc - 1 else 'OK'})"
        )

        # Lookahead
        look_block = ""
        if lookahead:
            look_lines = [
                f"  [{i+1}] {p.get('type','?')} → {p.get('target_concepts',[])}"
                for i, p in enumerate(lookahead)
            ]
            look_block = "\nUPCOMING STEPS:\n" + "\n".join(look_lines)

        # Mastery
        mastery_lines = [f"  {c}: {v:.2f}" for c, v in state.mastery_snapshot.items()]
        mastery_block = "MASTERY:\n" + "\n".join(mastery_lines) if mastery_lines else "MASTERY: (none)"

        # Recent conversation
        hist_block = "RECENT CONVERSATION: (none)"
        if state.recent_turns:
            lines = []
            for t in state.recent_turns[-3:]:
                lines.append(
                    f"  Student: {(t.get('student_message') or '')[:80]}\n"
                    f"  Tutor [{t.get('pedagogical_action','?')}/{t.get('current_step','?')}]: "
                    f"{(t.get('tutor_response') or '')[:80]}"
                )
            hist_block = "RECENT CONVERSATION:\n" + "\n".join(lines)

        # Evaluation
        eval_block = "EVALUATION: (none — first turn or no question was pending)"
        if state.latest_evaluation:
            ev = state.latest_evaluation
            eval_block = (
                f"EVALUATION OF STUDENT'S ANSWER:\n"
                f"  Score: {ev.get('overall_score', '?')}, Label: {ev.get('correctness_label', '?')}\n"
                f"  Feedback: {(ev.get('overall_feedback') or '')[:150]}\n"
                f"  Misconceptions: {ev.get('misconceptions', [])}"
            )

        return f"""{journey_block}

{obj_block}

{step_block}
{intermediate_block}{look_block}

{mastery_block}

{hist_block}

{eval_block}

STUDENT MESSAGE: "{state.student_message}"

Based on all the above, decide the pedagogical_action and progression_decision for this turn."""

    async def decide(self, state: PolicyState) -> PolicyOrchestratorOutput:
        return await self.run(state)

    def _apply_decision_guards(
        self,
        state: PolicyState,
        output: PolicyOrchestratorOutput,
    ) -> PolicyOrchestratorOutput:
        """Validate/correct policy output for roadmap-safe progression."""
        cs = state.curriculum_slice or {}
        obj = cs.get("current_objective", {}) if isinstance(cs, dict) else {}
        roadmap = obj.get("step_roadmap") or []
        roadmap = roadmap if isinstance(roadmap, list) else []
        step_idx = int(getattr(state, "current_step_index", 0) or 0)
        ad_hoc_count = int(getattr(state, "ad_hoc_count", 0) or 0)
        max_ad_hoc = int(getattr(state, "max_ad_hoc_per_objective", 4) or 4)

        decision = output.progression_decision
        reasoning_suffix: list[str] = []

        # Guard 1: ad-hoc budget enforcement
        if (
            decision == ProgressionDecision.INSERT_AD_HOC
            and ad_hoc_count >= max_ad_hoc
        ):
            decision = ProgressionDecision.ADVANCE_STEP
            output.ad_hoc_step_type = None
            reasoning_suffix.append("guard:ad_hoc_budget_forced_advance")

        # Guard 2: forward-only skip with can_skip validation
        if decision == ProgressionDecision.SKIP_TO_STEP:
            target = output.skip_target_index
            valid_forward = isinstance(target, int) and target > step_idx
            valid_bounds = isinstance(target, int) and 0 <= target < len(roadmap)

            can_skip_window = False
            if valid_forward and valid_bounds:
                can_skip_window = all(
                    bool((roadmap[i] or {}).get("can_skip", False))
                    for i in range(step_idx, target)
                )

            if not (valid_forward and valid_bounds and can_skip_window):
                decision = ProgressionDecision.CONTINUE_STEP
                output.skip_target_index = None
                reasoning_suffix.append("guard:skip_rejected")

        output.progression_decision = decision

        # Fill student_intent if missing (lightweight heuristic)
        if not output.student_intent:
            output.student_intent = self._infer_student_intent(state)

        # Intent-aware progression adjustment for fluid tutoring behavior.
        if output.student_intent == "move_on":
            eval_score = None
            if state.latest_evaluation and isinstance(state.latest_evaluation, dict):
                raw_score = state.latest_evaluation.get("overall_score")
                if isinstance(raw_score, (int, float)):
                    eval_score = float(raw_score)
            avg_mastery = 0.0
            if state.mastery_snapshot and state.focus_concepts:
                vals = [
                    float(state.mastery_snapshot.get(c, 0.0) or 0.0)
                    for c in state.focus_concepts
                ]
                avg_mastery = (sum(vals) / len(vals)) if vals else 0.0
            turns_at_step = int(getattr(state, "turns_at_step", 0) or 0)
            if output.progression_decision in {
                ProgressionDecision.CONTINUE_STEP,
                ProgressionDecision.INSERT_AD_HOC,
            } and "guard:skip_rejected" not in reasoning_suffix:
                has_eval_checkpoint = eval_score is not None and eval_score >= 0.6
                has_mastery_checkpoint = avg_mastery >= 0.45
                has_engagement_checkpoint = turns_at_step >= 1 and avg_mastery >= 0.35
                is_ready = (
                    has_eval_checkpoint
                    or has_mastery_checkpoint
                    or has_engagement_checkpoint
                )
                if is_ready:
                    at_last_step = bool(roadmap) and step_idx >= len(roadmap) - 1
                    output.progression_decision = (
                        ProgressionDecision.ADVANCE_OBJECTIVE
                        if at_last_step
                        else ProgressionDecision.ADVANCE_STEP
                    )
                    reasoning_suffix.append("guard:move_on_promoted_progression")
                else:
                    output.progression_decision = ProgressionDecision.CONTINUE_STEP
                    output.recommended_strategy = "assessment"
                    reasoning_suffix.append("guard:move_on_requires_checkpoint")

        # Always keep target concepts bounded and non-empty when possible
        if output.target_concepts:
            output.target_concepts = output.target_concepts[:3]
        elif state.focus_concepts:
            output.target_concepts = state.focus_concepts[:3]

        if reasoning_suffix:
            output.reasoning = f"{output.reasoning} | {';'.join(reasoning_suffix)}"

        return output

    def _infer_student_intent(self, state: PolicyState) -> str:
        """Heuristic student intent classification for guard-safe defaults."""
        msg = (state.student_message or "").strip().lower()
        if any(
            k in msg
            for k in (
                "don't care",
                "dont care",
                "whatever",
                "unrelated",
                "off topic",
                "off-topic",
            )
        ):
            return "off_topic"
        if any(k in msg for k in ("frustrated", "annoyed", "this sucks", "hate this")):
            return "frustrated"
        if any(k in msg for k in ("move on", "next", "skip", "done")):
            return "move_on"
        if any(k in msg for k in ("confused", "don't get", "dont get", "stuck", "help")):
            return "confused"
        if "?" in msg or any(k in msg for k in ("why", "how", "what", "can you")):
            return "asking_question"
        if any(k in msg for k in ("i think", "my answer", "is it", "equals", "therefore")):
            return "answer_attempt"
        if any(k in msg for k in ("boring", "bored")):
            return "bored"
        return "engaged"

    def _fallback_policy(self, state: PolicyState) -> PolicyOrchestratorOutput:
        """Mastery-aware heuristic fallback when LLM is unavailable."""
        action = PedagogicalAction.EXPLAIN
        decision = ProgressionDecision.CONTINUE_STEP
        strategy = "direct"
        msg = state.student_message.lower()

        # Compute average mastery of focus concepts
        avg_mastery = 0.0
        if state.mastery_snapshot and state.focus_concepts:
            vals = [state.mastery_snapshot.get(c, 0.0) for c in state.focus_concepts]
            avg_mastery = sum(vals) / len(vals) if vals else 0.0

        # Check evaluation result
        eval_score = 0.5
        eval_label = "partial"
        if state.latest_evaluation:
            eval_score = state.latest_evaluation.get("overall_score", 0.5)
            eval_label = state.latest_evaluation.get("correctness_label", "partial")

        step = state.current_step
        reasoning_parts = [f"step={step}", f"avg_mastery={avg_mastery:.2f}", f"eval={eval_label}({eval_score:.1f})"]

        if step in {"motivate", "activate_prior"}:
            action = PedagogicalAction.MOTIVATE if step == "motivate" else PedagogicalAction.QUESTION
            strategy = "direct" if step == "motivate" else "socratic"
            if eval_label in ("correct", "partial") and eval_score >= 0.6:
                decision = ProgressionDecision.ADVANCE_STEP
                reasoning_parts.append("advancing: warm-up objective met")
        elif step in {"define", "explain", "connect", "compare_contrast", "derive"}:
            if eval_label == "correct" or avg_mastery >= 0.3:
                action = PedagogicalAction.EXPLAIN
                decision = ProgressionDecision.ADVANCE_STEP
                strategy = "socratic" if avg_mastery >= 0.2 else "direct"
                reasoning_parts.append("advancing: mastery sufficient or correct answer")
            elif "help" in msg or "confused" in msg:
                action = PedagogicalAction.HINT
                strategy = "scaffolded"
            else:
                action = PedagogicalAction.EXPLAIN
                strategy = "scaffolded" if avg_mastery < 0.2 else "socratic"
        elif step in {"worked_example"}:
            action = PedagogicalAction.EXAMPLE
            strategy = "scaffolded"
            if eval_label in ("correct", "partial") and eval_score >= 0.65:
                decision = ProgressionDecision.ADVANCE_STEP
                reasoning_parts.append("advancing: example comprehension sufficient")
        elif step in {"probe", "practice", "correct", "reflect"}:
            action = PedagogicalAction.QUESTION
            if step == "correct":
                action = PedagogicalAction.CORRECT
            strategy = "socratic" if avg_mastery >= 0.3 else "scaffolded"
            if eval_label == "correct" or avg_mastery >= 0.5:
                decision = ProgressionDecision.ADVANCE_STEP
                reasoning_parts.append("advancing: good practice performance")
        elif step in {"assess"}:
            action = PedagogicalAction.ASSESS
            strategy = "assessment"
            if eval_label == "correct" or avg_mastery >= 0.7:
                decision = ProgressionDecision.ADVANCE_STEP
                reasoning_parts.append("advancing: assessment passed")
        elif step in {"summarize"}:
            action = PedagogicalAction.SUMMARIZE
            decision = ProgressionDecision.ADVANCE_STEP
            strategy = "review"
            reasoning_parts.append("advancing: review complete")
        elif "?" in state.student_message:
            action = PedagogicalAction.EXPLAIN
            strategy = "direct"

        return PolicyOrchestratorOutput(
            pedagogical_action=action,
            progression_decision=decision,
            confidence=0.5,
            reasoning=f"Fallback heuristic: {', '.join(reasoning_parts)}",
            intent="question" if "?" in state.student_message else "statement",
            recommended_strategy=strategy,
            target_concepts=state.focus_concepts[:3] if state.focus_concepts else None,
        )
