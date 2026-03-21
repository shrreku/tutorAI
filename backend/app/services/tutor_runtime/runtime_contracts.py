from __future__ import annotations

from copy import deepcopy
from typing import Any


def _stringify_resource_ids(resource_ids: list[Any] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for resource_id in resource_ids or []:
        if not resource_id:
            continue
        value = str(resource_id)
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def build_curriculum_scope(
    *,
    anchor_resource_id: Any | None,
    scope_type: str | None = None,
    scope_resource_ids: list[Any] | None = None,
    notebook_id: Any | None = None,
    topic: str | None = None,
    selected_topics: list[str] | None = None,
) -> dict[str, Any]:
    resource_ids = _stringify_resource_ids(scope_resource_ids)
    if not resource_ids and anchor_resource_id:
        resource_ids = [str(anchor_resource_id)]
    normalized_scope_type = (scope_type or "").strip() or (
        "notebook" if len(resource_ids) > 1 and notebook_id else "single_resource"
    )
    return {
        "scope_type": normalized_scope_type,
        "notebook_id": str(notebook_id) if notebook_id else None,
        "anchor_resource_id": str(anchor_resource_id) if anchor_resource_id else None,
        "resource_ids": resource_ids,
        "topic": topic,
        "selected_topics": list(selected_topics or []),
    }


def resolve_plan_scope(
    plan: dict[str, Any],
    notebook_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    notebook_context = notebook_context or {}
    stored_scope = plan.get("curriculum_scope") or {}
    resource_ids = _stringify_resource_ids(
        stored_scope.get("resource_ids") or notebook_context.get("resource_ids") or []
    )
    if not resource_ids and plan.get("resource_id"):
        resource_ids = [str(plan.get("resource_id"))]
    notebook_id = stored_scope.get("notebook_id") or notebook_context.get("notebook_id")
    anchor_resource_id = stored_scope.get("anchor_resource_id") or plan.get(
        "resource_id"
    )
    scope_type = stored_scope.get("scope_type") or (
        "notebook" if len(resource_ids) > 1 and notebook_id else "single_resource"
    )
    return {
        "scope_type": scope_type,
        "notebook_id": str(notebook_id) if notebook_id else None,
        "anchor_resource_id": str(anchor_resource_id) if anchor_resource_id else None,
        "resource_ids": resource_ids,
        "topic": stored_scope.get("topic") or plan.get("active_topic"),
        "selected_topics": list(stored_scope.get("selected_topics") or []),
    }


def sync_runtime_contract_views(
    plan: dict[str, Any],
    *,
    mastery_snapshot: dict[str, float] | None = None,
) -> dict[str, Any]:
    scope = resolve_plan_scope(plan)
    objective_queue = deepcopy(plan.get("objective_queue") or [])
    objective_progress = deepcopy(plan.get("objective_progress") or {})
    mastery_snapshot = dict(mastery_snapshot or {})
    weak_concepts = [
        concept
        for concept, score in mastery_snapshot.items()
        if float(score or 0.0) < 0.4
    ]
    plan["curriculum_scope"] = scope
    plan["curriculum_plan"] = {
        "version": 1,
        "active_topic": plan.get("active_topic"),
        "objective_queue": objective_queue,
        "scope": deepcopy(scope),
        "plan_provisional": bool(plan.get("plan_provisional", False)),
    }
    plan["session_runtime_state"] = {
        "version": 1,
        "mode": plan.get("mode"),
        "current_objective_index": int(plan.get("current_objective_index", 0) or 0),
        "current_step_index": int(plan.get("current_step_index", 0) or 0),
        "current_step": plan.get("current_step"),
        "effective_step_type": plan.get("effective_step_type"),
        "turns_at_step": int(plan.get("turns_at_step", 0) or 0),
        "step_status": deepcopy(plan.get("step_status") or {}),
        "ad_hoc_count": int(plan.get("ad_hoc_count", 0) or 0),
        "max_ad_hoc_per_objective": int(plan.get("max_ad_hoc_per_objective", 0) or 0),
        "awaiting_evaluation": bool(plan.get("awaiting_evaluation", False)),
        "focus_concepts": list(plan.get("focus_concepts") or []),
        "last_decision": plan.get("last_decision"),
        "last_transition": plan.get("last_transition"),
        "last_ad_hoc_type": plan.get("last_ad_hoc_type"),
        "replan_required": bool(plan.get("replan_required", False)),
        "last_replan_request": deepcopy(plan.get("last_replan_request") or {}),
        "last_scope_shift": deepcopy(plan.get("last_scope_shift") or {}),
    }
    plan["notebook_learning_state"] = {
        "version": 1,
        "notebook_id": scope.get("notebook_id"),
        "scope_type": scope.get("scope_type"),
        "resource_ids": list(scope.get("resource_ids") or []),
        "mastery_snapshot": mastery_snapshot,
        "objective_progress_snapshot": objective_progress,
        "weak_concepts": weak_concepts,
    }
    return plan


def build_policy_progression_intent(
    policy_output: Any, plan: dict[str, Any]
) -> dict[str, Any]:
    decision = getattr(policy_output, "progression_decision", None)
    decision_name = decision.name if hasattr(decision, "name") else str(decision or "")
    scope_shift_request = getattr(policy_output, "scope_shift_request", None) or {}
    replan_reason = getattr(policy_output, "replan_reason", None)
    replan_required = bool(getattr(policy_output, "replan_required", False))
    return {
        "decision": decision_name,
        "skip_target_index": getattr(policy_output, "skip_target_index", None),
        "next_objective_index": getattr(policy_output, "next_objective_index", None),
        "ad_hoc_step_type": getattr(policy_output, "ad_hoc_step_type", None),
        "student_intent": getattr(policy_output, "student_intent", None),
        "replan_required": replan_required,
        "replan_reason": replan_reason,
        "scope_shift_request": deepcopy(scope_shift_request),
        "current_scope": deepcopy(resolve_plan_scope(plan)),
    }


def build_retrieval_contract(
    *,
    query: str,
    target_concepts: list[str],
    pedagogy_roles: list[str],
    resource_ids: list[str],
    scope_type: str,
    notebook_id: str | None,
    objective_id: str | None,
    objective_title: str | None,
    policy_output: Any | None,
    retrieved_chunks: list[Any] | None = None,
) -> dict[str, Any]:
    directives = getattr(policy_output, "retrieval_directives", None) or {}
    return {
        "query": query,
        "target_concepts": list(target_concepts or []),
        "pedagogy_roles": list(pedagogy_roles or []),
        "scope_type": scope_type,
        "notebook_id": notebook_id,
        "resource_ids": list(resource_ids or []),
        "objective_id": objective_id,
        "objective_title": objective_title,
        "directives": deepcopy(directives),
        "retrieved_chunk_ids": [
            str(chunk.chunk_id)
            for chunk in (retrieved_chunks or [])
            if getattr(chunk, "chunk_id", None) is not None
        ],
    }


def build_response_contract(
    *,
    policy_output: Any,
    tutor_output: Any,
    evidence_chunk_ids: list[str] | None,
) -> dict[str, Any]:
    turn_plan = getattr(policy_output, "turn_plan", None)
    if hasattr(turn_plan, "model_dump"):
        turn_plan = turn_plan.model_dump()
    return {
        "pedagogical_action": getattr(policy_output, "pedagogical_action", None),
        "recommended_strategy": getattr(policy_output, "recommended_strategy", None),
        "planner_guidance": getattr(policy_output, "planner_guidance", None),
        "turn_plan": deepcopy(turn_plan),
        "tutor_question": getattr(tutor_output, "tutor_question", None),
        "evidence_chunk_ids": list(evidence_chunk_ids or []),
    }


def build_transition_contract(
    *,
    requested_decision: str | None,
    applied_decision: str | None,
    transition: str | None,
    guard_events: list[dict[str, Any]] | None,
    session_complete: bool,
    plan: dict[str, Any],
) -> dict[str, Any]:
    guard_events = [event for event in (guard_events or []) if isinstance(event, dict)]
    guard_labels = [
        event.get("guard_name")
        for event in guard_events
        if event.get("name") == "guard_override" and event.get("guard_name")
    ]
    accepted = (requested_decision or applied_decision) == applied_decision
    return {
        "requested_decision": requested_decision,
        "applied_decision": applied_decision,
        "accepted": bool(accepted),
        "transition": transition,
        "guard_labels": guard_labels,
        "rejection_reason": guard_labels[0] if guard_labels and not accepted else None,
        "session_complete": session_complete,
        "replan_required": bool(plan.get("replan_required", False)),
        "last_replan_request": deepcopy(plan.get("last_replan_request") or {}),
        "last_scope_shift": deepcopy(plan.get("last_scope_shift") or {}),
    }


def build_study_map_delta(
    before_plan: dict[str, Any],
    after_plan: dict[str, Any],
    *,
    transition: str | None,
    transition_contract: dict[str, Any],
) -> dict[str, Any]:
    before_scope = resolve_plan_scope(before_plan)
    after_scope = resolve_plan_scope(after_plan)
    return {
        "transition": transition,
        "from": {
            "objective_index": int(before_plan.get("current_objective_index", 0) or 0),
            "step_index": int(before_plan.get("current_step_index", 0) or 0),
            "scope": before_scope,
        },
        "to": {
            "objective_index": int(after_plan.get("current_objective_index", 0) or 0),
            "step_index": int(after_plan.get("current_step_index", 0) or 0),
            "scope": after_scope,
        },
        "changed": {
            "objective": int(before_plan.get("current_objective_index", 0) or 0)
            != int(after_plan.get("current_objective_index", 0) or 0),
            "step": int(before_plan.get("current_step_index", 0) or 0)
            != int(after_plan.get("current_step_index", 0) or 0),
            "scope": before_scope != after_scope,
        },
        "transition_contract": deepcopy(transition_contract),
    }
