from datetime import datetime, timezone

from app.services.student_state import (
    MIN_UNCERTAINTY,
    DEFAULT_MASTERY_MEAN,
    DEFAULT_MASTERY_UNCERTAINTY,
    build_student_concept_state,
    apply_uncertainty_aware_updates,
)


def test_student_concept_state_bootstrap_has_uncertainty_fields():
    state = build_student_concept_state({"conduction": 0.3})

    assert state["conduction"]["mastery_mean"] == 0.3
    assert 0.0 <= state["conduction"]["mastery_uncertainty"] <= 1.0
    assert state["conduction"]["last_practiced_at"] is None


def test_uncertainty_aware_update_reduces_uncertainty_for_correct_answers():
    base = build_student_concept_state({"conduction": 0.4})
    before_uncertainty = base["conduction"]["mastery_uncertainty"]
    practiced_at = datetime(2026, 2, 16, 0, 0, tzinfo=timezone.utc)

    updated = apply_uncertainty_aware_updates(
        base,
        {"conduction": {"delta": 0.2, "weight": 1.0, "role": "primary"}},
        correctness_label="correct",
        practiced_at=practiced_at,
    )

    assert updated["conduction"]["mastery_mean"] > 0.4
    assert updated["conduction"]["mastery_uncertainty"] < before_uncertainty
    assert updated["conduction"]["last_practiced_at"] == practiced_at.isoformat()


def test_uncertainty_aware_update_is_bounded_for_incorrect_answers():
    state = {
        "conduction": {
            "mastery_mean": 0.02,
            "mastery_uncertainty": 0.99,
            "last_practiced_at": None,
        }
    }

    updated = apply_uncertainty_aware_updates(
        state,
        {"conduction": {"delta": -1.0, "weight": 1.0, "role": "primary"}},
        correctness_label="incorrect",
    )

    assert 0.0 <= updated["conduction"]["mastery_mean"] <= 1.0
    assert MIN_UNCERTAINTY <= updated["conduction"]["mastery_uncertainty"] <= 1.0


def test_uncertainty_aware_update_preserves_untouched_concepts():
    state = build_student_concept_state({"a": 0.4, "b": 0.8})
    untouched_before = dict(state["b"])

    updated = apply_uncertainty_aware_updates(
        state,
        {"a": {"delta": 0.1, "weight": 1.0, "role": "primary"}},
        correctness_label="partial",
    )

    assert updated["b"] == untouched_before
