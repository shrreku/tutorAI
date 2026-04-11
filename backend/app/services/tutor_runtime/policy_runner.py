from __future__ import annotations

from typing import Any, Protocol, Sequence

from app.schemas.agent_output import EvaluatorOutput, PolicyOrchestratorOutput
from app.schemas.agent_state import PolicyState

from app.services.mastery import check_prereq_gate, compute_average_mastery
from app.services.tutor_runtime.events import append_trace_event
from app.services.tutor_runtime.guardrails import build_guard_override_metadata

from app.services.tutor_runtime.policy_reranker import rerank_policy_output
from app.services.tutor_runtime.step_state import build_curriculum_slice, get_step_index


class PolicyAgentProtocol(Protocol):
    async def decide(self, state: PolicyState) -> PolicyOrchestratorOutput: ...


def _dump_evaluation_result(
    value: EvaluatorOutput | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return None


def _apply_prereq_gate_to_policy_output(
    *,
    plan: dict[str, Any],
    policy_output: PolicyOrchestratorOutput,
    current_obj: dict[str, Any],
    mastery_snap: dict[str, float],
    prereq_threshold: float = 0.5,
) -> PolicyOrchestratorOutput:
    """Steer the current turn toward unmet prerequisites.

    This runs BEFORE retrieval/response so it can prevent undefined-jargon drift
    on the current turn.

    It is intentionally a *soft* gate: it does not invent new objectives; it
    redirects target concepts + retrieval query toward prerequisites and denies
    forward progression decisions when prereqs are clearly unmet.
    """

    scope = (current_obj.get("concept_scope") or {}) if isinstance(current_obj, dict) else {}
    prereq_concepts = scope.get("prereq") or []
    prereq_concepts = [c for c in prereq_concepts if isinstance(c, str) and c.strip()]
    if not prereq_concepts:
        return policy_output

    prereq_ok = check_prereq_gate(
        mastery=mastery_snap or {},
        prereq_concepts=prereq_concepts,
        threshold=prereq_threshold,
    )
    if prereq_ok:
        return policy_output

    avg_prereq_mastery = compute_average_mastery(mastery_snap or {}, prereq_concepts)
    requested = policy_output.progression_decision
    requested_name = requested.name if hasattr(requested, "name") else str(requested)

    # Deny forward progression decisions when prerequisites are unmet.
    # (We avoid INSERT_AD_HOC here to prevent exhausting ad-hoc budget.)
    applied = requested
    if requested_name in {"ADVANCE_STEP", "ADVANCE_OBJECTIVE", "SKIP_TO_STEP"}:
        from app.schemas.agent_output import ProgressionDecision

        applied = ProgressionDecision.CONTINUE_STEP
        policy_output.progression_decision = applied

    # Steer retrieval + tutoring to define/activate prerequisite concepts first.
    top_prereqs = prereq_concepts[:3]
    policy_output.target_concepts = top_prereqs

    existing_guidance = (getattr(policy_output, "planner_guidance", None) or "").strip()
    gate_guidance = (
        "Prereq gate: student likely lacks prerequisites. "
        f"Before using advanced jargon, briefly define and ground: {', '.join(top_prereqs)}. "
        "Then ask a quick check question to confirm understanding."
    ).strip()
    policy_output.planner_guidance = (
        f"{gate_guidance}\n{existing_guidance}".strip() if existing_guidance else gate_guidance
    )

    existing_directives = getattr(policy_output, "retrieval_directives", None) or {}
    if not isinstance(existing_directives, dict):
        existing_directives = {}
    directive_query = (
        existing_directives.get("query")
        or f"Definitions + intuition + minimal examples for: {', '.join(top_prereqs)}"
    )
    policy_output.retrieval_directives = {
        **existing_directives,
        "query": directive_query,
        "focus": "prereq",
        "expand_prereqs": True,
    }

    append_trace_event(
        plan,
        "guard_override",
        build_guard_override_metadata(
            guard_name="prereq_gate_not_met",
            decision_requested=requested_name,
            decision_applied=(applied.name if hasattr(applied, "name") else str(applied)),
            reason="prereq_gate_not_met",
            details={
                "objective_id": current_obj.get("objective_id"),
                "prereq_concepts": top_prereqs,
                "prereq_threshold": prereq_threshold,
                "avg_prereq_mastery": round(float(avg_prereq_mastery), 3),
            },
        ),
    )

    return policy_output


async def run_policy(
    policy_agent: PolicyAgentProtocol,
    plan: dict[str, Any],
    student_message: str,
    focus_concepts: list[str],
    mastery_snap: dict[str, float],
    evaluation_result: EvaluatorOutput | dict[str, Any] | None,
    current_obj: dict[str, Any],
    recent_turns: Sequence[dict[str, Any]] | None,
    *,
    max_ad_hoc_default: int,
    lf: Any,
) -> tuple[PolicyOrchestratorOutput, dict[str, Any]]:
    """Run policy agent with rich metadata and optional tracing span."""
    step_idx = get_step_index(plan)
    pol_meta = {
        "objective_id": current_obj.get("objective_id"),
        "step_type": plan.get("current_step"),
        "step_index": step_idx,
        "has_evaluation": evaluation_result is not None,
    }
    pol_span_ctx = None
    guard_span_ctx = None
    guard_span = None
    if lf:
        pol_span_ctx = lf.start_as_current_observation(
            as_type="span", name="agent.policy", metadata=pol_meta
        )
        pol_span_ctx.__enter__()

    try:
        objective_queue = plan.get("objective_queue", [])
        obj_idx = plan.get("current_objective_index", 0)
        objective_queue_summary = [
            {
                "id": o.get("objective_id", ""),
                "title": o.get("title", ""),
                "primary_concepts": o.get("concept_scope", {}).get("primary", []),
                "is_current": i == obj_idx,
                "is_completed": i < obj_idx,
            }
            for i, o in enumerate(objective_queue)
        ]

        policy_state = PolicyState(
            student_message=student_message,
            session_mode=str(plan.get("mode") or "learn"),
            current_step_index=step_idx,
            current_step=plan.get("current_step", "explain"),
            curriculum_slice=build_curriculum_slice(current_obj, step_idx),
            concept_scope=current_obj.get("concept_scope", {}),
            focus_concepts=focus_concepts,
            mastery_snapshot=mastery_snap,
            recent_turns=recent_turns or [],
            latest_evaluation=_dump_evaluation_result(evaluation_result),
            awaiting_evaluation=bool(plan.get("awaiting_evaluation", False)),
            pending_tutor_question=plan.get("pending_tutor_question"),
            pending_tutor_response=plan.get("pending_tutor_response"),
            current_objective_index=obj_idx,
            total_objectives=len(objective_queue),
            objective_queue_summary=objective_queue_summary,
            turns_at_step=plan.get("turns_at_step", 0),
            learner_personalization=plan.get("learner_personalization"),
            ad_hoc_count=plan.get("ad_hoc_count", 0),
            max_ad_hoc_per_objective=plan.get(
                "max_ad_hoc_per_objective", max_ad_hoc_default
            ),
            last_decision=plan.get("last_decision"),
        )
        policy_output = await policy_agent.decide(policy_state)
        rerank_result = rerank_policy_output(
            policy_output,
            plan=plan,
            evaluation_result=evaluation_result,
        )
        policy_output = rerank_result.policy_output

        policy_output = _apply_prereq_gate_to_policy_output(
            plan=plan,
            policy_output=policy_output,
            current_obj=current_obj,
            mastery_snap=mastery_snap,
            prereq_threshold=float(
                (plan.get("mode_contract") or {}).get("prereq_gate_threshold", 0.5)
                or 0.5
            ),
        )

        policy_metadata = {
            "reranker_enabled": rerank_result.enabled,
            "reranker_changed": rerank_result.changed,
            "rerank_reason": rerank_result.reason,
            "decision_requested": rerank_result.requested_decision,
            "decision_applied": rerank_result.applied_decision,
            "student_intent": getattr(policy_output, "student_intent", None),
            "candidate_scores": rerank_result.candidate_scores,
        }
        if lf:
            guard_span_ctx = lf.start_as_current_observation(
                as_type="span",
                name="agent.policy.guardrails",
                metadata={
                    "decision_requested": policy_metadata.get("decision_requested"),
                    "decision_applied": policy_metadata.get("decision_applied"),
                    "student_intent": policy_metadata.get("student_intent"),
                    "reranker_changed": policy_metadata.get("reranker_changed", False),
                    "ad_hoc_count": plan.get("ad_hoc_count", 0),
                    "max_ad_hoc_per_objective": plan.get(
                        "max_ad_hoc_per_objective", max_ad_hoc_default
                    ),
                },
            )
            guard_span = guard_span_ctx.__enter__()
            guard_span.update(
                output={
                    "candidate_scores": policy_metadata.get("candidate_scores", {}),
                    "skip_target_index": getattr(
                        policy_output, "skip_target_index", None
                    ),
                    "ad_hoc_step_type": getattr(
                        policy_output, "ad_hoc_step_type", None
                    ),
                }
            )
    finally:
        if guard_span_ctx:
            guard_span_ctx.__exit__(None, None, None)
        if pol_span_ctx:
            pol_span_ctx.__exit__(None, None, None)

    return policy_output, policy_metadata
