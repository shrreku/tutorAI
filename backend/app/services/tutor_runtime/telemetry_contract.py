from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_label(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_turn_telemetry_contract(
    *,
    decision_requested: str | None,
    decision_applied: str | None,
    student_intent: str | None,
    guard_events: list[dict[str, Any]],
    evidence_chunk_ids: list[str],
    mastery_delta: dict[str, float],
    uncertainty_before: dict[str, float],
    uncertainty_after: dict[str, float],
    forgetting_supported: bool = False,
) -> dict[str, Any]:
    """Build compact, low-cardinality turn telemetry contract payload (v4)."""
    guard_names = sorted(
        {
            _safe_label(event.get("guard_name"))
            for event in (guard_events or [])
            if isinstance(event, dict) and event.get("name") == "guard_override"
        }
    )
    guard_names = [name for name in guard_names if name]

    touched_concepts = sorted(mastery_delta.keys())
    delta_values = [
        _safe_float(mastery_delta.get(concept), 0.0)
        for concept in touched_concepts
    ]
    positive = sum(1 for value in delta_values if value > 0)
    negative = sum(1 for value in delta_values if value < 0)

    uncertainty_changes = {}
    for concept in sorted(set(uncertainty_before) | set(uncertainty_after)):
        before = _safe_float(uncertainty_before.get(concept), 0.0)
        after = _safe_float(uncertainty_after.get(concept), before)
        uncertainty_changes[concept] = round(after - before, 6)

    uncertainty_values = list(uncertainty_changes.values())

    contract = {
        "version": 4,
        "decision_requested": _safe_label(decision_requested),
        "decision_applied": _safe_label(decision_applied),
        "student_intent": _safe_label(student_intent),
        "guard_override_count": len(guard_names),
        "guard_names": guard_names,
        "evidence_count": len(set(evidence_chunk_ids or [])),
        "concepts_touched": touched_concepts,
        "mastery_delta_sum": round(sum(delta_values), 6),
        "mastery_positive_count": positive,
        "mastery_negative_count": negative,
        "uncertainty_delta_sum": round(sum(uncertainty_values), 6),
        "forgetting_supported": forgetting_supported,
    }
    return contract
