"""
Summary Agent — generates a personalized session wrap-up when a session completes.

Instead of a hardcoded "Congratulations!" message, this agent receives the full
session context (objectives, mastery, conversation highlights) and produces a
warm, honest, pedagogically-sound closing response.
"""
import logging
from typing import Optional, Dict, Any, List

from langfuse import observe
from pydantic import BaseModel, Field, ConfigDict

from app.agents.base import BaseAgent
from app.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


# ── State & Output schemas ────────────────────────────────────────────

class SummaryState(BaseModel):
    """Input to the Summary Agent."""
    model_config = ConfigDict(extra="ignore")

    objectives: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Objective queue with titles, descriptions, concept scopes",
    )
    objective_progress: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-objective progress: {obj_id: {attempts, correct, steps_completed, ...}}",
    )
    mastery: Dict[str, float] = Field(
        default_factory=dict,
        description="Final concept mastery values (0-1)",
    )
    initial_mastery: Dict[str, float] = Field(
        default_factory=dict,
        description="Mastery values at session start (usually all 0)",
    )
    turn_count: int = Field(default=0, description="Total turns in the session")
    topic: Optional[str] = Field(default=None, description="Session topic")
    key_moments: List[str] = Field(
        default_factory=list,
        description="Notable turn summaries (correct answers, breakthroughs)",
    )


class SummaryOutput(BaseModel):
    """Output from the Summary Agent."""
    model_config = ConfigDict(extra="forbid")

    summary_text: str = Field(
        ..., min_length=1,
        description="The personalized session wrap-up message",
    )
    concepts_strong: List[str] = Field(
        default_factory=list,
        description="Concepts the student showed strength in (mastery >= 0.5)",
    )
    concepts_developing: List[str] = Field(
        default_factory=list,
        description="Concepts still developing (mastery < 0.5 but > 0)",
    )
    concepts_to_revisit: List[str] = Field(
        default_factory=list,
        description="Concepts that need more work (mastery < 0.25)",
    )


# ── System prompt ─────────────────────────────────────────────────────

SUMMARY_SYSTEM_PROMPT = """You are the **Session Summary** writer for an adaptive tutoring system.
The student has just finished a tutoring session. Write a warm, honest, and specific wrap-up message.

# Your goals
1. **Celebrate what went well.** Name specific concepts the student understood or got right.
2. **Be honest about what's still developing.** Low mastery isn't failure — it means those concepts were introduced but not yet deeply practiced. Frame this positively as "next steps."
3. **Summarise the learning journey.** Briefly recap the objectives covered and the main ideas explored.
4. **Keep it concise.** 3-5 short paragraphs maximum. No bullet lists — write naturally.
5. **End with encouragement** and a clear suggestion for what to do next (e.g., "A quick quiz on these topics would help solidify what you've learned.").

# Tone
- Conversational, like a supportive teacher wrapping up a lesson
- Specific, not generic — reference actual concept names and what was discussed
- No over-the-top praise or empty platitudes

# Output
Write your summary as plain text (markdown is fine). Do NOT output JSON."""


class SummaryAgent(BaseAgent[SummaryState, SummaryOutput]):
    """Generates a personalised session wrap-up."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        super().__init__("Summary")
        self.llm = llm_provider

    @property
    def system_prompt(self) -> str:
        return SUMMARY_SYSTEM_PROMPT

    @observe(name="agent.summary", capture_input=False)
    async def run(self, state: SummaryState) -> SummaryOutput:
        logger.info("SummaryAgent: generating session wrap-up")

        # Classify concepts by mastery level
        concepts_strong = []
        concepts_developing = []
        concepts_to_revisit = []
        for concept, value in state.mastery.items():
            if value >= 0.5:
                concepts_strong.append(concept)
            elif value >= 0.15:
                concepts_developing.append(concept)
            elif value > 0:
                concepts_to_revisit.append(concept)

        if self.llm:
            try:
                text = await self.llm.generate(
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": self._build_prompt(state, concepts_strong, concepts_developing, concepts_to_revisit)},
                    ],
                    temperature=0.7,
                    max_tokens=1024,
                    trace_name="agent.summary.generate",
                    trace_metadata={"turn_count": state.turn_count, "topic": state.topic},
                )

                if text and text.strip():
                    return SummaryOutput(
                        summary_text=text.strip(),
                        concepts_strong=concepts_strong,
                        concepts_developing=concepts_developing,
                        concepts_to_revisit=concepts_to_revisit,
                    )
            except Exception as e:
                logger.warning(f"LLM summary generation failed: {e}, using fallback")

        return self._fallback(state, concepts_strong, concepts_developing, concepts_to_revisit)

    def _build_prompt(
        self,
        state: SummaryState,
        concepts_strong: list[str],
        concepts_developing: list[str],
        concepts_to_revisit: list[str],
    ) -> str:
        # Build objectives summary
        obj_lines = []
        for i, obj in enumerate(state.objectives, 1):
            title = obj.get("title", "Untitled")
            obj_id = obj.get("objective_id", f"obj_{i}")
            progress = state.objective_progress.get(obj_id, {})
            correct = progress.get("correct", 0)
            attempts = progress.get("attempts", 0)
            steps_done = progress.get("steps_completed", 0)
            obj_lines.append(
                f"  {i}. {title} — {steps_done} steps completed, "
                f"{correct}/{attempts} correct responses"
            )

        # Build mastery summary
        mastery_lines = []
        for concept, value in sorted(state.mastery.items(), key=lambda x: -x[1]):
            if value > 0:
                initial = state.initial_mastery.get(concept, 0.0)
                delta = value - initial
                label = "Strong" if value >= 0.5 else "Developing" if value >= 0.15 else "Introduced"
                mastery_lines.append(
                    f"  - {concept}: {value:.0%} ({label}, +{delta:.0%} this session)"
                )

        return f"""SESSION SUMMARY DATA:

Topic: {state.topic or 'N/A'}
Total turns: {state.turn_count}

OBJECTIVES COVERED:
{chr(10).join(obj_lines) if obj_lines else '  (none)'}

CONCEPT MASTERY (end of session):
{chr(10).join(mastery_lines) if mastery_lines else '  (no mastery data)'}

STRONG CONCEPTS (≥50%): {', '.join(c.replace('_', ' ') for c in concepts_strong) or 'none yet'}
DEVELOPING CONCEPTS (15-50%): {', '.join(c.replace('_', ' ') for c in concepts_developing) or 'none'}
NEEDS REVISIT (<15%): {', '.join(c.replace('_', ' ') for c in concepts_to_revisit) or 'none'}

{('KEY MOMENTS:' + chr(10) + chr(10).join('  - ' + m for m in state.key_moments)) if state.key_moments else ''}

Write the session summary now."""

    def _fallback(
        self,
        state: SummaryState,
        concepts_strong: list[str],
        concepts_developing: list[str],
        concepts_to_revisit: list[str],
    ) -> SummaryOutput:
        """Deterministic fallback when LLM is unavailable."""
        topic = state.topic or "this material"
        obj_count = len(state.objectives)
        turn_count = state.turn_count

        parts = [
            f"Great work completing this session on **{topic}**! "
            f"Over {turn_count} turns, we covered {obj_count} learning objective{'s' if obj_count != 1 else ''}."
        ]

        if concepts_strong:
            names = ", ".join(c.replace("_", " ") for c in concepts_strong[:3])
            parts.append(
                f"You showed solid understanding of **{names}** — those foundations are in good shape."
            )

        if concepts_developing:
            names = ", ".join(c.replace("_", " ") for c in concepts_developing[:3])
            parts.append(
                f"Concepts like **{names}** are developing nicely. "
                "A bit more practice will help lock them in."
            )

        if concepts_to_revisit:
            names = ", ".join(c.replace("_", " ") for c in concepts_to_revisit[:3])
            parts.append(
                f"We touched on **{names}** briefly — these are great candidates for your next study session."
            )

        parts.append(
            "Try a quick quiz on this topic to reinforce what you've learned and identify any remaining gaps!"
        )

        return SummaryOutput(
            summary_text="\n\n".join(parts),
            concepts_strong=concepts_strong,
            concepts_developing=concepts_developing,
            concepts_to_revisit=concepts_to_revisit,
        )
