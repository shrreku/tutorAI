from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.services.mastery import ROLE_WEIGHTS


MIN_MASTERY = 0.0
MAX_MASTERY = 1.0
MIN_UNCERTAINTY = 0.05
MAX_UNCERTAINTY = 1.0
DEFAULT_UNCERTAINTY = 0.7
DEFAULT_MASTERY_MEAN = 0.0
DEFAULT_MASTERY_UNCERTAINTY = DEFAULT_UNCERTAINTY


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _default_state(mean: float = 0.0) -> dict[str, Any]:
    return {
        "mastery_mean": _clamp(mean, MIN_MASTERY, MAX_MASTERY),
        "mastery_uncertainty": DEFAULT_UNCERTAINTY,
        "last_practiced_at": None,
    }


def concept_mastery_mean(value: Any) -> float:
    if isinstance(value, dict):
        return _clamp(
            _as_float(value.get("mastery_mean"), 0.0), MIN_MASTERY, MAX_MASTERY
        )
    return _clamp(_as_float(value, 0.0), MIN_MASTERY, MAX_MASTERY)


def build_student_concept_state(
    initial_mastery: dict[str, float],
) -> dict[str, dict[str, Any]]:
    return ensure_student_concept_state(
        existing_state=None, mastery_snapshot=initial_mastery
    )


def ensure_student_concept_state(
    existing_state: Optional[dict[str, Any]],
    mastery_snapshot: Optional[dict[str, float]] = None,
) -> dict[str, dict[str, Any]]:
    """Return normalized concept state with mastery mean/uncertainty/last_practiced."""
    normalized: dict[str, dict[str, Any]] = {}

    if isinstance(existing_state, dict):
        for concept, payload in existing_state.items():
            if not isinstance(concept, str):
                continue

            if isinstance(payload, dict):
                mastery_mean = concept_mastery_mean(payload)
                mastery_uncertainty = _clamp(
                    _as_float(payload.get("mastery_uncertainty"), DEFAULT_UNCERTAINTY),
                    MIN_UNCERTAINTY,
                    MAX_UNCERTAINTY,
                )
                last_practiced_at = payload.get("last_practiced_at")
                if not isinstance(last_practiced_at, str):
                    last_practiced_at = None
                normalized[concept] = {
                    "mastery_mean": mastery_mean,
                    "mastery_uncertainty": mastery_uncertainty,
                    "last_practiced_at": last_practiced_at,
                }
            else:
                normalized[concept] = _default_state(concept_mastery_mean(payload))

    for concept, mastery in (mastery_snapshot or {}).items():
        mastery_mean = concept_mastery_mean(mastery)
        if concept not in normalized:
            normalized[concept] = _default_state(mastery_mean)
        else:
            normalized[concept]["mastery_mean"] = mastery_mean

    return normalized


def mastery_snapshot_from_student_state(
    concept_state: dict[str, Any],
) -> dict[str, float]:
    normalized = ensure_student_concept_state(concept_state)
    return {
        concept: _clamp(
            _as_float(state.get("mastery_mean"), 0.0), MIN_MASTERY, MAX_MASTERY
        )
        for concept, state in normalized.items()
    }


def apply_uncertainty_aware_updates(
    concept_state: dict[str, Any],
    concept_deltas: dict[str, dict[str, Any]],
    *,
    correctness_label: str,
    alpha: float = 0.7,
    practiced_at: Optional[datetime] = None,
) -> dict[str, dict[str, Any]]:
    """Apply bounded updates to concept mastery and uncertainty for touched concepts only."""
    updated = ensure_student_concept_state(concept_state)
    timestamp = (practiced_at or datetime.now(timezone.utc)).isoformat()

    for concept, delta_info in concept_deltas.items():
        current = updated.get(concept, _default_state())
        role_weight = delta_info.get("role_weight") or ROLE_WEIGHTS.get(
            delta_info.get("role", "support"),
            0.7,
        )
        weight = _clamp(_as_float(delta_info.get("weight", 1.0), 1.0), 0.0, 1.0)
        delta = _as_float(delta_info.get("delta", 0.0), 0.0)

        change = alpha * role_weight * weight * delta
        new_mean = _clamp(
            concept_mastery_mean(current) + change,
            MIN_MASTERY,
            MAX_MASTERY,
        )

        signal_strength = _clamp(
            abs(delta) * max(0.25, weight) * max(0.25, role_weight), 0.0, 1.0
        )
        old_uncertainty = _clamp(
            _as_float(current.get("mastery_uncertainty"), DEFAULT_UNCERTAINTY),
            MIN_UNCERTAINTY,
            MAX_UNCERTAINTY,
        )

        if correctness_label == "correct":
            uncertainty_shift = -(0.06 + (0.08 * signal_strength))
        elif correctness_label == "partial":
            uncertainty_shift = -(0.03 + (0.04 * signal_strength))
        elif correctness_label == "incorrect":
            uncertainty_shift = 0.04 + (0.08 * signal_strength)
        else:
            uncertainty_shift = 0.02 + (0.02 * signal_strength)

        updated[concept] = {
            "mastery_mean": new_mean,
            "mastery_uncertainty": _clamp(
                old_uncertainty + uncertainty_shift,
                MIN_UNCERTAINTY,
                MAX_UNCERTAINTY,
            ),
            "last_practiced_at": timestamp,
        }

    return updated
