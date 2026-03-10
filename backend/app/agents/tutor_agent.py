import logging
from typing import Optional, List, Dict, Any

from langfuse import observe

from app.agents.base import BaseAgent
from app.schemas.agent_state import TutorState
from app.schemas.agent_output import TutorOutput
from app.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


# ── Strategy-specific instructions embedded in the system prompt ──────
# Research-backed: Direct Instruction, Scaffolding (Vygotsky ZPD),
# Socratic Questioning, Retrieval Practice, Elaborative Interrogation.

TUTOR_SYSTEM_PROMPT = """You are an expert **Tutor** in an adaptive tutoring system.
Write a natural, conversational tutoring response to the student.

# Session structure
The session follows **learning objectives**, each with a flexible **step roadmap**.
You are told the current objective, canonical step type, effective step type, target concepts, and source material.

# Core rules
1. **Stay on-objective.** Teach the concepts in the current objective.
2. **Follow the step type.** Adjust your depth and approach accordingly (see below).
3. **Ground in source material when available.** Use the retrieved knowledge chunks. When source material is limited or unavailable, teach using the objective context, concept descriptions, and your pedagogical knowledge — but be transparent about any limitations if the student asks for specific source details.
4. **Be concise and natural.** Avoid generic filler or repetitive boilerplate.
5. **Connect concepts.** Relate the current topic to what the student already knows.
6. **End with engagement.** When appropriate, close with a question that matches the strategy and step type. Do NOT force a question if it doesn't fit (e.g. after a simple introduction, a warm invitation to ask questions is fine).
7. **Never refuse to teach.** Even with limited evidence, you can always explain a concept, ask a question, provide intuition, or engage the student. Use the objective and curriculum context to stay helpful.

# Step-type behaviour
- **motivate / activate_prior**: Build interest and connect to what the learner already knows.
- **define / explain**: Clarify terms, mechanisms, and intuition.
- **worked_example / derive / compare_contrast**: Show structured reasoning and explicit links.
- **probe / practice / assess**: Elicit student thinking, then evaluate understanding.
- **correct / reflect / connect / summarize**: Repair misconceptions, consolidate, and transfer learning.
- If canonical and effective step type differ, prioritize the **effective step type** for this turn.

# Pedagogical strategies (use what the policy recommends)
- **direct**: Explicit teaching. Present information clearly, demonstrate procedures, then check understanding with a targeted question.
- **socratic**: Ask probing questions that guide the student to discover the answer themselves. Types: clarifying ("What do you mean by…?"), assumption-probing ("Why do you think that's true?"), evidence-probing ("What supports that?"), implication-exploring ("What would follow if…?").
- **scaffolded**: Break the task into smaller parts. Provide a worked sub-step, then ask the student to complete the next part. Gradually remove support as they succeed.
- **assessment**: Pose a clear problem. Let the student attempt it before offering help. If they struggle, give a small hint and let them try again.
- **review**: Recap what was learned, highlight key connections, ask the student to summarise in their own words.

# Session mode contract
- `learn`: explain clearly, introduce concepts in order, and avoid turning every reply into a quiz.
- `doubt`: answer the confusion directly first, then verify understanding with one compact follow-up if needed.
- `practice`: keep the learner doing the work. Ask for an attempt, reveal only the next helpful hint, and avoid over-explaining too early.
- `revision`: compress, compare, and test recall. Prefer concise summaries and retrieval prompts over long first-teach explanations.

# Output format
Write your response as **plain text** (markdown is fine). Do NOT output JSON.
Just write your tutoring response directly."""


class TutorAgent(BaseAgent[TutorState, TutorOutput]):
    """Tutor agent that generates responses to students."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        super().__init__("Tutor")
        self.llm = llm_provider

    @property
    def system_prompt(self) -> str:
        return TUTOR_SYSTEM_PROMPT

    @observe(name="agent.tutor", capture_input=False)
    async def run(self, state: TutorState) -> TutorOutput:
        logger.info(f"TutorAgent: step={state.current_step}, msg={state.student_message[:50]}...")

        if self.llm:
            try:
                text = await self.llm.generate(
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": self._build_prompt(state)},
                    ],
                    temperature=0.7,
                    max_tokens=2048,
                    trace_name="agent.tutor.generate",
                    trace_metadata={
                        "step_type": state.effective_step_type or state.current_step,
                        "step_index": getattr(state, "current_step_index", 0),
                        "strategy": state.recommended_strategy,
                    },
                )
                if text and text.strip():
                    return TutorOutput(
                        response_text=text.strip(),
                        evidence_chunk_ids=state.evidence_chunk_ids,
                    )
            except Exception as e:
                logger.warning(f"LLM tutor generation failed: {e}, using fallback")

        return self._fallback_response(state)

    def _build_prompt(self, state: TutorState) -> str:
        cs = state.curriculum_slice
        obj = cs.get("current_objective", {})
        step = cs.get("current_step", {})
        scope = obj.get("concept_scope", {})
        step_index = cs.get("current_step_index", 0)
        effective_step_type = state.effective_step_type or state.current_step

        # Strategy instruction
        strategy = state.recommended_strategy or "direct"
        strategy_line = f"STRATEGY: {strategy}"

        # Objective & step context
        ctx = (
            f"SESSION MODE: {state.session_mode}\n"
            f"OBJECTIVE: {obj.get('title', 'N/A')}\n"
            f"  {obj.get('description', '')}\n"
            f"  Primary concepts: {scope.get('primary', [])}\n\n"
            f"CURRENT STEP: {step.get('type', state.current_step)} "
            f"(step {step_index})\n"
            f"EFFECTIVE STEP THIS TURN: {effective_step_type}\n"
            f"  Target concepts: {step.get('target_concepts', [])}\n"
            f"  Goal: {step.get('goal', 'N/A')}"
        )

        # Target concepts from policy
        targets = f"\nTARGET CONCEPTS THIS TURN: {state.target_concepts or 'same as step'}"

        # Guidance from policy
        guidance = ""
        if state.planner_guidance:
            guidance = f"\nPOLICY GUIDANCE: {state.planner_guidance}"
        if state.turn_plan:
            goal = state.turn_plan.get("goal", "")
            itype = state.turn_plan.get("interaction_type", "")
            if goal:
                guidance += f"\nTURN GOAL: {goal}"
            if itype:
                guidance += f"\nINTERACTION TYPE: {itype}"
        if state.ad_hoc_step_type:
            guidance += f"\nAD-HOC STEP TYPE: {state.ad_hoc_step_type}"

        # Retrieved knowledge
        chunks = state.retrieved_chunks
        if chunks:
            chunk_lines = []
            for i, c in enumerate(chunks[:5], 1):
                text = c.get("text", "")[:500]
                chunk_id = c.get("chunk_id", f"chunk_{i}")
                chunk_lines.append(f"[{i}] ({chunk_id}) {text}")
            knowledge = "RETRIEVED KNOWLEDGE:\n" + "\n\n".join(chunk_lines)
        else:
            knowledge = "RETRIEVED KNOWLEDGE: (none available)"

        return f"""{strategy_line}

{ctx}{targets}{guidance}

{knowledge}

STUDENT MESSAGE: "{state.student_message}"

Write your tutoring response now."""

    async def generate(self, state: TutorState) -> TutorOutput:
        return await self.run(state)

    def _fallback_response(self, state: TutorState) -> TutorOutput:
        step = state.effective_step_type or state.current_step
        mode = (state.session_mode or "learn").strip().lower()
        if mode == "doubt":
            response = (
                "Let’s resolve the exact sticking point first. Here is the shortest accurate explanation of that idea, "
                "and then I’ll check whether the confusion is gone."
            )
        elif mode == "practice":
            response = (
                "Try the next step yourself first. Show me your attempt, and I’ll give only the smallest hint needed to keep you moving."
            )
        elif mode == "revision":
            response = (
                "Quick revision pass: state the key idea in one or two sentences, then we’ll test whether you can retrieve it cleanly without support."
            )
        elif step in {"motivate", "activate_prior"}:
            response = (
                "Great starting point. Before we dive in, what related idea do you already feel confident about? "
                "We'll use that as our bridge into this concept."
            )
        elif step in {"probe", "practice"}:
            response = (
                "Let's try a focused checkpoint. Walk me through your reasoning step by step, "
                "and I will help refine it if needed."
            )
        elif step == "assess":
            response = (
                "Let's check your understanding. Can you work through "
                "this problem and explain your reasoning?"
            )
        elif "?" in state.student_message:
            response = (
                "Good question! Let me help clarify that. "
                "What specific part would you like me to explain first?"
            )
        else:
            response = (
                "Thank you for your response. Let's continue building on that. "
                "Can you explain that concept in your own words?"
            )
        return TutorOutput(
            response_text=response,
            evidence_chunk_ids=state.evidence_chunk_ids,
        )
