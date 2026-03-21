from __future__ import annotations

from typing import Any, Protocol, Sequence

from app.schemas.agent_output import (
    EvaluatorOutput,
    PolicyOrchestratorOutput,
    ProgressionDecision,
)
from app.schemas.agent_state import PolicyState

from app.services.mastery import check_prereq_gate, compute_average_mastery
from app.services.tutor_runtime.events import append_trace_event

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

    It is intentionally a *soft* steer: it does not invent new objectives or
    rewrite the policy's progression decision.
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
        "policy_guidance",
        {
            "guidance_name": "prereq_support",
            "objective_id": current_obj.get("objective_id"),
            "decision_requested": requested_name,
            "prereq_concepts": top_prereqs,
            "prereq_threshold": prereq_threshold,
            "avg_prereq_mastery": round(float(avg_prereq_mastery), 3),
        },
    )

    return policy_output


def _apply_pending_checkpoint_guidance(
    *,
    plan: dict[str, Any],
    policy_output: PolicyOrchestratorOutput,
) -> PolicyOrchestratorOutput:
    awaiting_evaluation = bool(plan.get("awaiting_evaluation", False))
    student_intent = getattr(policy_output, "student_intent", None)
    pending_question = str(plan.get("last_tutor_question") or "").strip()
    if not awaiting_evaluation or student_intent != "move_on" or not pending_question:
        return policy_output

    if policy_output.progression_decision in {
        ProgressionDecision.CONTINUE_STEP,
        ProgressionDecision.INSERT_AD_HOC,
    }:
        binary_choice_guidance = (
            "The learner wants to move on while a checkpoint is pending. Keep this reply concise and operational. "
            "Offer exactly two options: (1) answer the pending checkpoint now, or (2) skip ahead with a brief note that mastery may be incomplete. "
            "Do not give another long justification for staying on the same step."
        )
        existing_guidance = (getattr(policy_output, "planner_guidance", None) or "").strip()
        policy_output.planner_guidance = (
            f"{binary_choice_guidance}\n{existing_guidance}".strip()
            if existing_guidance
            else binary_choice_guidance
        )
        if getattr(policy_output, "recommended_strategy", None) in {None, "assessment", "socratic"}:
            policy_output.recommended_strategy = "direct"
        append_trace_event(
            plan,
            "policy_guidance",
            {
                "guidance_name": "pending_checkpoint_binary_choice",
                "decision_requested": (
                    policy_output.progression_decision.name
                    if hasattr(policy_output.progression_decision, "name")
                    else str(policy_output.progression_decision)
                ),
                "pending_question": pending_question[:200],
            },
        )

    return policy_output


def _apply_doubt_adjacent_guidance(
    *,
    plan: dict[str, Any],
    policy_output: PolicyOrchestratorOutput,
    current_obj: dict[str, Any],
) -> PolicyOrchestratorOutput:
    if str(plan.get("mode") or "learn").strip().lower() != "doubt":
        return policy_output

    target_concepts = [
        str(concept).strip()
        for concept in (getattr(policy_output, "target_concepts", None) or [])
        if str(concept).strip()
    ]
    retrieval_directives = getattr(policy_output, "retrieval_directives", None) or {}
    if not isinstance(retrieval_directives, dict):
        retrieval_directives = {}

    scope = (current_obj.get("concept_scope") or {}) if isinstance(current_obj, dict) else {}
    objective_concepts = {
        str(concept).strip()
        for concept in (
            (scope.get("primary") or [])
            + (scope.get("support") or [])
            + (scope.get("prereq") or [])
        )
        if str(concept).strip()
    }
    adjacent_concepts = [
        concept for concept in target_concepts if concept not in objective_concepts
    ]
    ad_hoc_step_type = str(getattr(policy_output, "ad_hoc_step_type", "") or "").strip().lower()
    retrieval_focus = str(retrieval_directives.get("focus") or "").strip().lower()
    prerequisite_signal = (
        retrieval_focus == "prereq"
        or "prereq" in ad_hoc_step_type
        or ad_hoc_step_type == "clarification_of_domain"
    )
    mostly_adjacent = bool(target_concepts) and len(adjacent_concepts) >= max(
        1, (len(target_concepts) + 1) // 2
    )
    if not prerequisite_signal and not mostly_adjacent:
        return policy_output

    adjacent_label = ", ".join(adjacent_concepts[:3]) or "the background idea"
    guidance = (
        "Doubt mode handling: first resolve the student's immediate confusion briefly and concretely. "
        f"Be explicit that {adjacent_label} is background or adjacent to the current notebook objective, not the main topic of this session. "
        "After the short clarification, recommend starting a learn session if the student wants a fuller walkthrough from first principles. "
        "Do not refuse help; answer the immediate doubt, then offer the learn-session path."
    )
    existing_guidance = (getattr(policy_output, "planner_guidance", None) or "").strip()
    policy_output.planner_guidance = (
        f"{guidance}\n{existing_guidance}".strip()
        if existing_guidance
        else guidance
    )

    if getattr(policy_output, "recommended_strategy", None) in {None, "socratic"}:
        policy_output.recommended_strategy = "direct"

    if getattr(policy_output, "turn_plan", None) is not None:
        constraints = list(policy_output.turn_plan.constraints or [])
        for item in (
            "Keep the prerequisite clarification brief before returning to the notebook topic.",
            "Recommend a learn session for a fuller walkthrough if the student wants deeper coverage.",
        ):
            if item not in constraints:
                constraints.append(item)
        policy_output.turn_plan.constraints = constraints

    policy_output.retrieval_directives = {
        **retrieval_directives,
        "focus": retrieval_directives.get("focus") or "prereq",
        "expand_prereqs": True,
    }

    append_trace_event(
        plan,
        "guard_override",
        build_guard_override_metadata(
            guard_name="doubt_adjacent_guidance",
            decision_requested=(
                policy_output.progression_decision.name
                if hasattr(policy_output.progression_decision, "name")
                else str(policy_output.progression_decision)
            ),
            decision_applied=(
                policy_output.progression_decision.name
                if hasattr(policy_output.progression_decision, "name")
                else str(policy_output.progression_decision)
            ),
            reason="doubt_question_is_prerequisite_or_adjacent",
            details={
                "objective_id": current_obj.get("objective_id"),
                "adjacent_concepts": adjacent_concepts[:5],
                "retrieval_focus": retrieval_focus,
                "ad_hoc_step_type": ad_hoc_step_type,
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
            current_objective_index=obj_idx,
            total_objectives=len(objective_queue),
            objective_queue_summary=objective_queue_summary,
            turns_at_step=plan.get("turns_at_step", 0),
            ad_hoc_count=plan.get("ad_hoc_count", 0),
            max_ad_hoc_per_objective=plan.get(
                "max_ad_hoc_per_objective", max_ad_hoc_default
            ),
            last_decision=plan.get("last_decision"),
            awaiting_evaluation=bool(plan.get("awaiting_evaluation", False)),
            pending_tutor_question=plan.get("last_tutor_question"),
            pending_tutor_response=plan.get("last_tutor_response"),
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
        policy_output = _apply_doubt_adjacent_guidance(
            plan=plan,
            policy_output=policy_output,
            current_obj=current_obj,
        )
        policy_output = _apply_pending_checkpoint_guidance(
            plan=plan,
            policy_output=policy_output,
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
