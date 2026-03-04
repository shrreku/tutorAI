import logging
from typing import Optional

from app.schemas.agent_output import ProgressionDecision
from app.services.mastery import check_success_criteria
from app.services.tutor_runtime.guardrails import (
    build_guard_override_metadata,
    enforce_ad_hoc_budget,
    enforce_step_turn_limit,
    is_valid_skip_target,
)
from app.services.tutor_runtime.events import append_trace_event
from app.services.tutor_runtime.step_state import (
    build_step_status,
    get_max_turns_for_step,
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
    max_turns_at_step = get_max_turns_for_step(roadmap, old_step_idx)

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
        "max_turns_at_step": max_turns_at_step,
    }

    prog_span_ctx = None
    prog_span = None
    if lf:
        prog_span_ctx = lf.start_as_current_observation(
            as_type="span", name="turn.progression", metadata=prog_meta
        )
        prog_span = prog_span_ctx.__enter__()

    try:
        decision = policy_output.progression_decision

        pre_guard_decision_name = decision.name
        decision, forced_by_ad_hoc_budget = enforce_ad_hoc_budget(
            decision,
            ad_hoc_count=ad_hoc_count,
            max_ad_hoc=max_ad_hoc,
        )
        if forced_by_ad_hoc_budget:
            logger.info(
                f"[progression] Reconnection: {ad_hoc_count} consecutive "
                f"intermediates reached limit, forcing ADVANCE_STEP"
            )
            guard_names.append("forced_return_from_ad_hoc_budget")
            append_trace_event(
                plan,
                "guard_override",
                build_guard_override_metadata(
                    guard_name="forced_return_from_ad_hoc_budget",
                    decision_requested=pre_guard_decision_name,
                    decision_applied=decision.name,
                    reason="ad_hoc_budget_exhausted",
                    details={
                        "from_step_index": old_step_idx,
                        "ad_hoc_count": ad_hoc_count,
                        "limit": max_ad_hoc,
                    },
                ),
            )

        pre_guard_decision_name = decision.name
        decision, forced_by_turn_limit = enforce_step_turn_limit(
            decision,
            turns_at_step=turns_at_step,
            max_turns_at_step=max_turns_at_step,
        )
        if forced_by_turn_limit:
            logger.info(
                f"[progression] Max-turns guard: step {old_step_idx} "
                f"reached {turns_at_step + 1}/{max_turns_at_step}, forcing ADVANCE_STEP"
            )
            guard_names.append("forced_advance_max_turns")
            append_trace_event(
                plan,
                "guard_override",
                build_guard_override_metadata(
                    guard_name="forced_advance_max_turns",
                    decision_requested=pre_guard_decision_name,
                    decision_applied=decision.name,
                    reason="step_max_turns_reached",
                    details={
                        "from_step_index": old_step_idx,
                        "turns_at_step": turns_at_step + 1,
                        "max_turns_at_step": max_turns_at_step,
                    },
                ),
            )

        if (
            decision == ProgressionDecision.ADVANCE_OBJECTIVE
            and roadmap
            and old_step_idx < len(roadmap) - 1
        ):
            decision = ProgressionDecision.ADVANCE_STEP
            guard_names.append("objective_readiness_not_met")
            append_trace_event(
                plan,
                "guard_override",
                build_guard_override_metadata(
                    guard_name="objective_readiness_not_met",
                    decision_requested=ProgressionDecision.ADVANCE_OBJECTIVE.name,
                    decision_applied=decision.name,
                    reason="remaining_required_steps",
                    details={
                        "from_step_index": old_step_idx,
                        "last_step_index": len(roadmap) - 1,
                    },
                ),
            )

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
                # Roadmap complete — advance to next objective.
                # Success criteria are advisory; the policy drove the ADVANCE_STEP.
                success = check_success_criteria(
                    plan.get("objective_progress", {}).get(obj_id, {}),
                    current_obj.get("success_criteria", {}),
                    session.mastery,
                    current_obj.get("concept_scope", {}).get("primary", []),
                )
                if not success:
                    logger.info(
                        f"[progression] Objective {obj_id} advancing despite unmet "
                        f"success criteria (policy-driven fluid progression)"
                    )
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
                        {"attempts": 0, "correct": 0, "steps_completed": 0, "steps_skipped": 0},
                    )
                    progress["steps_skipped"] = int(progress.get("steps_skipped", 0)) + skipped
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
            # Trust the policy's decision to advance the objective.
            # Success criteria are advisory — logged for observability.
            success = check_success_criteria(
                plan.get("objective_progress", {}).get(obj_id, {}),
                current_obj.get("success_criteria", {}),
                session.mastery,
                current_obj.get("concept_scope", {}).get("primary", []),
            )
            if not success:
                logger.info(
                    f"[progression] Policy advancing objective {obj_id} despite "
                    f"unmet success criteria (fluid progression)"
                )
                append_trace_event(
                    plan,
                    "advisory_note",
                    {
                        "note": "objective_advanced_without_success_criteria",
                        "objective_id": obj_id,
                        "objective_index": old_obj_idx,
                    },
                )
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

        elif decision in (ProgressionDecision.CONTINUE_STEP, ProgressionDecision.INSERT_AD_HOC):
            plan["turns_at_step"] = int(plan.get("turns_at_step", 0)) + 1
            if decision == ProgressionDecision.INSERT_AD_HOC:
                plan["ad_hoc_count"] = ad_hoc_count + 1
                plan["last_ad_hoc_type"] = getattr(policy_output, "ad_hoc_step_type", None)
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
                plan["last_ad_hoc_type"] = None
                transition = f"step:{old_step_idx} (continue)"

        elif decision == ProgressionDecision.END_SESSION:
            plan["ad_hoc_count"] = 0
            session_complete = True
            transition = "session:ended_by_policy"

        plan["last_decision"] = decision.name
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
