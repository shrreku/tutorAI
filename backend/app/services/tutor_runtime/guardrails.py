from app.schemas.agent_output import ProgressionDecision


GUARD_PRECEDENCE = {
    "safety_block": 1,
    "schema_contract": 2,
    "objective_readiness_not_met": 3,
    "objective_success_criteria_not_met": 3,
    "forced_advance_max_turns": 4,
    "forced_return_from_ad_hoc_budget": 4,
    "skip_rejected_by_guard": 4,
}


def enforce_ad_hoc_budget(
    decision: ProgressionDecision,
    *,
    ad_hoc_count: int,
    max_ad_hoc: int,
) -> tuple[ProgressionDecision, bool]:
    """Force ADVANCE_STEP when ad-hoc budget is exhausted."""
    if decision == ProgressionDecision.INSERT_AD_HOC and ad_hoc_count >= max_ad_hoc:
        return ProgressionDecision.ADVANCE_STEP, True
    return decision, False


def enforce_step_turn_limit(
    decision: ProgressionDecision,
    *,
    turns_at_step: int,
    max_turns_at_step: int,
) -> tuple[ProgressionDecision, bool]:
    """Force ADVANCE_STEP when a step reaches max_turns."""
    if (
        decision in (ProgressionDecision.CONTINUE_STEP, ProgressionDecision.INSERT_AD_HOC)
        and (turns_at_step + 1) >= max_turns_at_step
    ):
        return ProgressionDecision.ADVANCE_STEP, True
    return decision, False


def is_valid_skip_target(target: int | None, *, step_idx: int, roadmap: list[dict]) -> bool:
    """Validate a skip target against current roadmap bounds."""
    if not (isinstance(target, int) and 0 <= target < len(roadmap) and target > step_idx):
        return False

    return all(
        bool((roadmap[i] or {}).get("can_skip", False))
        for i in range(step_idx, target)
    )


def build_guard_override_metadata(
    *,
    guard_name: str,
    decision_requested: str,
    decision_applied: str,
    reason: str,
    why_not_advanced: str | None = None,
    next_required_signal: str | None = None,
    details: dict | None = None,
) -> dict:
    """Build stable metadata payload for guard override trace events."""
    payload = {
        "guard_name": guard_name,
        "decision_requested": decision_requested,
        "decision_applied": decision_applied,
        "reason": reason,
        "guard_priority": GUARD_PRECEDENCE.get(guard_name, 99),
    }
    if why_not_advanced:
        payload["why_not_advanced"] = why_not_advanced
    if next_required_signal:
        payload["next_required_signal"] = next_required_signal
    if details:
        payload.update(details)
    return payload


def is_low_evidence(evidence_chunk_ids: list[str], *, minimum_count: int = 1) -> tuple[bool, str | None]:
    """Return whether retrieval evidence is below threshold for grounded responses."""
    evidence_count = len(evidence_chunk_ids)
    if evidence_count < minimum_count:
        return True, f"evidence_count_below_minimum:{evidence_count}<{minimum_count}"
    return False, None
