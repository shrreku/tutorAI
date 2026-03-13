from __future__ import annotations

from typing import Any, Protocol

from app.models.session import UserSession
from app.schemas.agent_output import EvaluatorOutput
from app.schemas.agent_state import EvaluatorState
from app.services.student_state import (
    apply_uncertainty_aware_updates,
    ensure_student_concept_state,
)


class EvaluatorAgentProtocol(Protocol):
    async def evaluate(self, state: EvaluatorState) -> EvaluatorOutput: ...


def _delta_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return getattr(value, "__dict__", {})


async def evaluate_response(
    evaluator_agent: EvaluatorAgentProtocol,
    session: UserSession,
    plan: dict[str, Any],
    student_message: str,
    focus_concepts: list[str],
    mastery_snap: dict[str, float],
    current_obj: dict[str, Any],
    *,
    lf: Any,
) -> tuple[EvaluatorOutput, dict[str, float]]:
    """Evaluate student response and apply mastery deltas.

    This stage is intentionally side-effect free for progression plan-state fields;
    orchestrator remains the single mutator for session progression state.
    """
    eval_meta = {
        "objective_id": current_obj.get("objective_id"),
        "tutor_question": (plan.get("last_tutor_question") or "")[:120],
        "focus_concepts": focus_concepts,
        "effective_step_type": plan.get(
            "effective_step_type",
            plan.get("current_step", "explain"),
        ),
    }
    eval_span_ctx = None
    if lf:
        eval_span_ctx = lf.start_as_current_observation(
            as_type="span",
            name="agent.evaluator",
            metadata=eval_meta,
            input={"student_message": student_message[:200]},
        )
        eval_span_ctx.__enter__()

    try:
        eval_state = EvaluatorState(
            student_message=student_message,
            current_step=plan.get("current_step", "explain"),
            effective_step_type=plan.get(
                "effective_step_type",
                plan.get("current_step", "explain"),
            ),
            tutor_question=plan.get("last_tutor_question"),
            tutor_response=plan.get("last_tutor_response"),
            current_objective=current_obj,
            concept_scope=current_obj.get("concept_scope", {}),
            focus_concepts=focus_concepts,
            mastery_snapshot=mastery_snap,
            retrieved_chunks=[],
        )
        evaluation_result = await evaluator_agent.evaluate(eval_state)

        mastery_delta = {}
        if evaluation_result.concept_deltas:
            deltas_dict = {
                c: _delta_payload(d)
                for c, d in evaluation_result.concept_deltas.items()
            }
            before_mastery = dict(session.mastery or {})
            concept_state = ensure_student_concept_state(
                plan.get("student_concept_state"),
                before_mastery,
            )
            updated_concept_state = apply_uncertainty_aware_updates(
                concept_state,
                deltas_dict,
                correctness_label=evaluation_result.correctness_label,
            )
            plan["student_concept_state"] = updated_concept_state

            touched = set(deltas_dict.keys())
            if session.mastery is None:
                session.mastery = {}
            for concept in touched:
                concept_state_entry = updated_concept_state.get(concept, {})
                session.mastery[concept] = concept_state_entry.get(
                    "mastery_mean",
                    before_mastery.get(concept, 0.0),
                )

            mastery_delta = {
                concept: round(
                    session.mastery.get(concept, 0.0)
                    - before_mastery.get(concept, 0.0),
                    6,
                )
                for concept in touched
            }

    finally:
        if eval_span_ctx:
            eval_span_ctx.__exit__(None, None, None)

    return evaluation_result, mastery_delta
