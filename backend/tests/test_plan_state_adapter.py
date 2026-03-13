import pytest

from app.services.tutor_runtime.step_state import normalize_runtime_plan_state


def test_normalize_plan_state_v3_only_cutover_rejects_legacy_versions():
    v2 = {
        "version": 2,
        "objective_queue": [
            {"objective_id": "o1", "step_roadmap": [{"type": "explain"}]}
        ],
        "current_objective_index": 0,
        "current_step_index": 0,
        "ad_hoc_count": 0,
        "step_status": {"0": "active"},
    }

    with pytest.raises(ValueError):
        normalize_runtime_plan_state(v2)


def test_normalize_plan_state_sets_defaults_when_missing():
    plan = {
        "objective_queue": [
            {"objective_id": "o1", "step_roadmap": [{"type": "practice"}]}
        ],
    }

    normalized = normalize_runtime_plan_state(plan)

    assert normalized["version"] == 3
    assert normalized["current_objective_index"] == 0
    assert normalized["current_step_index"] == 0
    assert normalized["current_step"] == "practice"
    assert normalized["ad_hoc_count"] == 0
