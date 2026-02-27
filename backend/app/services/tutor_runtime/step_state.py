from __future__ import annotations

from typing import Optional

from app.schemas.agent_output import ProgressionDecision
from app.services.tutor_runtime.plan_state_migration import (
    PLAN_STATE_VERSION,
    migrate_plan_state_to_v3,
)


def obj_meta(obj: dict, idx: int) -> dict:
    """Build rich metadata dict for an objective (used in Langfuse spans)."""
    scope = obj.get("concept_scope", {})
    roadmap = get_step_roadmap(obj)
    return {
        "objective_id": obj.get("objective_id", ""),
        "objective_index": idx,
        "title": obj.get("title", ""),
        "primary_concepts": scope.get("primary", []),
        "support_concepts": scope.get("support", []),
        "prereq_concepts": scope.get("prereq", []),
        "total_steps": len(roadmap),
        "success_criteria": obj.get("success_criteria", {}),
    }


def get_step_roadmap(obj: dict) -> list[dict]:
    """Return objective roadmap."""
    roadmap = obj.get("step_roadmap") or []
    return roadmap if isinstance(roadmap, list) else []


def get_step_type(step: dict) -> str:
    """Return step type for step-era roadmap."""
    return step.get("type") or "unknown"


def get_step_goal(step: dict) -> str:
    """Return step completion goal."""
    return step.get("goal") or ""


def get_step_index(plan: dict) -> int:
    """Return current step pointer."""
    return int(plan.get("current_step_index", 0) or 0)


def normalize_runtime_plan_state(plan_state: dict | None) -> dict:
    """Normalize session plan into strict runtime v3 shape."""
    plan = migrate_plan_state_to_v3(plan_state)

    objective_queue = plan.get("objective_queue")
    if not isinstance(objective_queue, list):
        objective_queue = []
    plan["objective_queue"] = objective_queue

    plan["version"] = PLAN_STATE_VERSION

    obj_idx = max(0, int(plan.get("current_objective_index", 0) or 0))
    if objective_queue and obj_idx >= len(objective_queue):
        obj_idx = len(objective_queue) - 1
    plan["current_objective_index"] = obj_idx

    step_idx = max(0, int(plan.get("current_step_index", 0) or 0))
    plan["current_step_index"] = step_idx

    plan["ad_hoc_count"] = max(0, int(plan.get("ad_hoc_count", 0) or 0))
    plan["turns_at_step"] = max(0, int(plan.get("turns_at_step", 0) or 0))
    plan["max_ad_hoc_per_objective"] = max(1, int(plan.get("max_ad_hoc_per_objective", 4) or 4))
    plan.setdefault("last_decision", None)

    current_obj = objective_queue[obj_idx] if obj_idx < len(objective_queue) else {}
    roadmap = get_step_roadmap(current_obj)
    if roadmap and step_idx >= len(roadmap):
        step_idx = len(roadmap) - 1
        plan["current_step_index"] = step_idx

    step = roadmap[step_idx] if roadmap and step_idx < len(roadmap) else {}
    plan["current_step"] = get_step_type(step) if step else "explain"

    step_status = plan.get("step_status")
    if not isinstance(step_status, dict) or not step_status:
        plan["step_status"] = build_step_status(roadmap, step_idx)

    plan.setdefault("objective_progress", {})
    plan.setdefault("focus_concepts", [])
    plan.setdefault("last_ad_hoc_type", None)
    plan.setdefault("student_concept_state", {})

    return plan


def build_step_status(
    roadmap: list[dict],
    active_idx: int,
    previous_status: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Build deterministic per-step status map for the current objective."""
    previous_status = previous_status or {}
    status: dict[str, str] = {}
    for idx in range(len(roadmap)):
        prior = previous_status.get(str(idx))
        if prior == "skipped":
            status[str(idx)] = "skipped"
        elif idx < active_idx:
            status[str(idx)] = "completed"
        elif idx == active_idx:
            status[str(idx)] = "active"
        else:
            status[str(idx)] = "upcoming"
    return status


def get_max_turns_for_step(roadmap: list[dict], step_idx: int, default: int = 5) -> int:
    """Return configured max_turns for the active roadmap step.

    Applies a minimum floor of 3 turns so the policy always has room
    for multi-turn Socratic interaction regardless of curriculum config.
    """
    floor = 3
    if 0 <= step_idx < len(roadmap):
        step = roadmap[step_idx] or {}
        value = step.get("max_turns", default)
        if isinstance(value, int) and value >= 1:
            return max(value, floor)
    return default


def required_steps_for_objective(roadmap: list[dict]) -> set[int]:
    """Indexes of required readiness steps before objective advancement."""
    required_types = {"practice", "assess"}
    return {
        idx
        for idx, step in enumerate(roadmap)
        if get_step_type(step) in required_types
    }


def required_steps_satisfied(step_status: dict, required_indexes: set[int]) -> bool:
    """Whether required readiness steps have been reached before advancing objective."""
    if not required_indexes:
        return True
    for idx in required_indexes:
        status = step_status.get(str(idx))
        if status not in {"completed", "active"}:
            return False
    return True


def compute_effective_step_type(canonical_step_type: str, policy_output=None) -> str:
    """Resolve the runtime-effective step type for this turn."""
    if policy_output is not None:
        decision = getattr(policy_output, "progression_decision", None)
        ad_hoc = getattr(policy_output, "ad_hoc_step_type", None)
        if ad_hoc and (
            decision is None or decision == ProgressionDecision.INSERT_AD_HOC
        ):
            return ad_hoc

    return canonical_step_type


def step_meta(obj: dict, step_idx: int) -> dict:
    """Build rich metadata dict for a step (used in Langfuse spans)."""
    roadmap = get_step_roadmap(obj)
    step = roadmap[step_idx] if step_idx < len(roadmap) else {}
    return {
        "step_index": step_idx,
        "step_type": get_step_type(step),
        "target_concepts": step.get("target_concepts", []),
        "goal": get_step_goal(step),
        "total_steps": len(roadmap),
    }


def build_curriculum_slice(obj: dict, step_idx: int) -> dict:
    """Build the curriculum slice dict passed to agents."""
    roadmap = get_step_roadmap(obj)
    step = roadmap[step_idx] if roadmap and step_idx < len(roadmap) else {}
    return {
        "current_objective": obj,
        "current_step_index": step_idx,
        "current_step": step,
        "lookahead_steps": roadmap[step_idx + 1: step_idx + 3] if roadmap else [],
    }


def build_focus_concepts(scope: dict) -> list[str]:
    """Build ordered unique list of focus concepts from concept scope."""
    return list(dict.fromkeys(
        scope.get("primary", [])
        + scope.get("support", [])
        + scope.get("prereq", [])
    ))


def update_objective_progress(plan: dict, current_obj: dict, evaluation_result) -> None:
    """Update objective progress counters from latest evaluator result."""
    obj_id = current_obj.get("objective_id", "")
    progress = plan.get("objective_progress", {})
    if obj_id not in progress:
        progress[obj_id] = {
            "attempts": 0,
            "correct": 0,
            "steps_completed": 0,
            "steps_skipped": 0,
        }

    progress[obj_id]["attempts"] += 1
    if evaluation_result.correctness_label in ("correct", "partial"):
        if evaluation_result.overall_score >= 0.7:
            progress[obj_id]["correct"] += 1

    plan["objective_progress"] = progress
