import logging
from typing import Optional

from app.schemas.agent_output import ProgressionDecision
from app.services.tutor_runtime.guardrails import (
    build_guard_override_metadata,
    is_valid_skip_target,
)
from app.services.tutor_runtime.events import append_trace_event
from app.services.tutor_runtime.step_state import (
    build_step_status,
    get_step_index,
    get_step_roadmap,
)

logger = logging.getLogger(__name__)


def apply_progression(
    session,
    plan: dict,
    policy_output,
    current_obj: dict,
    *,
    evaluation_result=None,
    progression_context: Optional[dict] = None,
    lf,
    max_ad_hoc_default: int,
) -> tuple[bool, dict, Optional[str]]:
    """
    Apply the policy progression decision.

    Returns (session_complete, updated_plan, transition_description).
    """
    session_complete = False
    transition = None
    old_obj_idx = plan.get("current_objective_index", 0)
    old_step_idx = get_step_index(plan)
    roadmap = get_step_roadmap(current_obj)
    obj_id = current_obj.get("objective_id", "")
    objective_queue = plan.get("objective_queue", [])
    ad_hoc_count = plan.get("ad_hoc_count", 0)
    max_ad_hoc = plan.get("max_ad_hoc_per_objective", max_ad_hoc_default)
    turns_at_step = int(plan.get("turns_at_step", 0))

    requested_decision = policy_output.progression_decision
    requested_decision_name = (
        requested_decision.name
        if hasattr(requested_decision, "name")
        else str(requested_decision)
    )
    applied_decision_name = requested_decision_name
    guard_names: list[str] = []

    prog_meta = {
        "from_objective_index": old_obj_idx,
        "from_step_index": old_step_idx,
        "decision_requested": requested_decision_name,
        "ad_hoc_count": ad_hoc_count,
        "max_ad_hoc_per_objective": max_ad_hoc,
        "turns_at_step": turns_at_step,
    }

    prog_span_ctx = None
    prog_span = None
    if lf:
        prog_span_ctx = lf.start_as_current_observation(
            as_type="span", name="turn.progression", metadata=prog_meta
        )
        prog_span = prog_span_ctx.__enter__()

    try:
        progression_context = progression_context or {}
        decision = policy_output.progression_decision
        student_intent = progression_context.get("student_intent") or getattr(
            policy_output, "student_intent", None
        )
        safety_blocked = bool(progression_context.get("safety_blocked", False))
        redirect_active = safety_blocked or student_intent == "off_topic"

        if redirect_active and decision in (
            ProgressionDecision.ADVANCE_STEP,
            ProgressionDecision.ADVANCE_OBJECTIVE,
        ):
            fallback_decision = (
                ProgressionDecision.INSERT_AD_HOC
                if requested_decision == ProgressionDecision.INSERT_AD_HOC
                else ProgressionDecision.CONTINUE_STEP
            )
            guard_names.append("redirect_in_progress")
            append_trace_event(
                plan,
                "guard_override",
                build_guard_override_metadata(
                    guard_name="redirect_in_progress",
                    decision_requested=decision.name,
                    decision_applied=fallback_decision.name,
                    reason="safety_or_off_topic_redirect_active",
                    details={
                        "student_intent": student_intent,
                        "safety_blocked": safety_blocked,
                    },
                ),
            )
            decision = fallback_decision

        if decision == ProgressionDecision.ADVANCE_STEP:
            plan["ad_hoc_count"] = 0
            plan["turns_at_step"] = 0
            progress_map = plan.setdefault("objective_progress", {})
            progress = progress_map.setdefault(
                obj_id,
                {"attempts": 0, "correct": 0, "steps_completed": 0, "steps_skipped": 0},
            )
            progress["steps_completed"] = int(progress.get("steps_completed", 0)) + 1
            new_step = old_step_idx + 1

            if new_step >= len(roadmap):
                plan["current_objective_index"] = old_obj_idx + 1
                plan["current_step_index"] = 0
                plan["step_status"] = {}
                transition = f"objective:{old_obj_idx}→{old_obj_idx + 1} (completed)"
                if plan["current_objective_index"] >= len(objective_queue):
                    session_complete = True
                    transition += " [session_complete]"
            else:
                plan["current_step_index"] = new_step
                transition = f"step:{old_step_idx}→{new_step}"

        elif decision == ProgressionDecision.SKIP_TO_STEP:
            target = getattr(policy_output, "skip_target_index", None)
            if is_valid_skip_target(target, step_idx=old_step_idx, roadmap=roadmap):
                plan["current_step_index"] = target
                skipped = max(0, target - old_step_idx - 1)
                prior_status = dict(plan.get("step_status", {}))
                if skipped:
                    progress_map = plan.setdefault("objective_progress", {})
                    progress = progress_map.setdefault(
                        obj_id,
                        {
                            "attempts": 0,
                            "correct": 0,
                            "steps_completed": 0,
                            "steps_skipped": 0,
                        },
                    )
                    progress["steps_skipped"] = (
                        int(progress.get("steps_skipped", 0)) + skipped
                    )
                plan["ad_hoc_count"] = 0
                plan["turns_at_step"] = 0
                if roadmap:
                    for idx in range(old_step_idx + 1, target):
                        prior_status[str(idx)] = "skipped"
                    prior_status[str(target)] = "active"
                    plan["step_status"] = prior_status
                transition = f"step:{old_step_idx}→{target} (skipped)"
            else:
                decision = ProgressionDecision.CONTINUE_STEP
                plan["turns_at_step"] = int(plan.get("turns_at_step", 0)) + 1
                transition = f"step:{old_step_idx} (skip denied)"
                guard_names.append("skip_rejected_by_guard")
                append_trace_event(
                    plan,
                    "guard_override",
                    build_guard_override_metadata(
                        guard_name="skip_rejected_by_guard",
                        decision_requested=ProgressionDecision.SKIP_TO_STEP.name,
                        decision_applied=decision.name,
                        reason="invalid_or_non_skippable_target",
                        details={
                            "from_step_index": old_step_idx,
                            "skip_target_index": target,
                        },
                    ),
                )

        elif decision == ProgressionDecision.ADVANCE_OBJECTIVE:
            plan["ad_hoc_count"] = 0
            plan["turns_at_step"] = 0
            plan["current_objective_index"] = old_obj_idx + 1
            plan["current_step_index"] = 0
            plan["step_status"] = {}
            transition = f"objective:{old_obj_idx}→{old_obj_idx + 1} (advance)"
            append_trace_event(
                plan,
                "objective_advanced",
                {
                    "from_objective_index": old_obj_idx,
                    "to_objective_index": old_obj_idx + 1,
                },
            )
            if plan["current_objective_index"] >= len(objective_queue):
                session_complete = True
                transition += " [session_complete]"

        elif decision in (
            ProgressionDecision.CONTINUE_STEP,
            ProgressionDecision.INSERT_AD_HOC,
        ):
            if decision == ProgressionDecision.INSERT_AD_HOC:
                plan["ad_hoc_count"] = ad_hoc_count + 1
                plan["last_ad_hoc_type"] = getattr(
                    policy_output, "ad_hoc_step_type", None
                )
                append_trace_event(
                    plan,
                    "ad_hoc_inserted",
                    {
                        "at_step_index": old_step_idx,
                        "ad_hoc_step_type": plan.get("last_ad_hoc_type"),
                        "ad_hoc_count": plan["ad_hoc_count"],
                    },
                )
                transition = (
                    f"step:{old_step_idx} (ad_hoc #{plan['ad_hoc_count']}"
                    f"/{max_ad_hoc}, stay)"
                )
            else:
                if not redirect_active:
                    plan["turns_at_step"] = int(plan.get("turns_at_step", 0)) + 1
                plan["last_ad_hoc_type"] = None
                transition = f"step:{old_step_idx} (continue)"

        elif decision == ProgressionDecision.END_SESSION:
            plan["ad_hoc_count"] = 0
            session_complete = True
            transition = "session:ended_by_policy"

        plan["last_decision"] = decision.name
        plan["last_transition"] = transition
        applied_decision_name = decision.name

        if not session_complete:
            current_idx = plan.get("current_objective_index", 0)
            if 0 <= current_idx < len(objective_queue):
                current_obj = objective_queue[current_idx]
                current_roadmap = get_step_roadmap(current_obj)
                current_step_idx = get_step_index(plan)
                plan["step_status"] = build_step_status(
                    current_roadmap,
                    current_step_idx,
                    previous_status=plan.get("step_status", {}),
                )

        logger.info(f"[progression] {transition}")

    finally:
        if prog_span_ctx:
            if prog_span:
                prog_span.update(
                    output={
                        "transition": transition,
                        "decision_requested": requested_decision_name,
                        "decision_applied": applied_decision_name,
                        "guard_name": "|".join(guard_names) if guard_names else None,
                        "new_objective_index": plan.get("current_objective_index"),
                        "new_step_index": get_step_index(plan),
                        "session_complete": session_complete,
                        "ad_hoc_count": plan.get("ad_hoc_count", 0),
                    }
                )
            prog_span_ctx.__exit__(None, None, None)

    return session_complete, plan, transition
