import importlib

import pytest

from app.services.tutor_runtime.scoring import emit_scores
from app.services.tutor_runtime.telemetry_contract import build_turn_telemetry_contract
from app.services.tutor_runtime.types import TurnResult


def test_turn_telemetry_contract_v4_contains_required_fields():
    contract = build_turn_telemetry_contract(
        decision_requested="CONTINUE_STEP",
        decision_applied="ADVANCE_STEP",
        student_intent="move_on",
        guard_events=[
            {
                "name": "guard_override",
                "guard_name": "forced_advance_max_turns",
            }
        ],
        evidence_chunk_ids=["c1", "c2", "c2"],
        mastery_delta={"conduction": 0.12, "convection": -0.03},
        uncertainty_before={"conduction": 0.7, "convection": 0.5},
        uncertainty_after={"conduction": 0.6, "convection": 0.55},
        forgetting_supported=False,
    )

    assert contract["version"] == 4
    assert contract["decision_requested"] == "CONTINUE_STEP"
    assert contract["decision_applied"] == "ADVANCE_STEP"
    assert contract["student_intent"] == "move_on"
    assert contract["guard_override_count"] == 1
    assert contract["guard_names"] == ["forced_advance_max_turns"]
    assert contract["evidence_count"] == 2
    assert contract["concepts_touched"] == ["conduction", "convection"]
    assert contract["mastery_delta_sum"] == pytest.approx(0.09)
    assert contract["uncertainty_delta_sum"] == pytest.approx(-0.05)
    assert contract["forgetting_supported"] is False


def test_scoring_emits_track_e_telemetry_scores(monkeypatch):
    numeric_calls = {}
    categorical_calls = {}

    def _score_trace(_trace_id, name, value, **_kwargs):
        numeric_calls[name] = value

    def _score_trace_categorical(_trace_id, name, value, **_kwargs):
        categorical_calls[name] = value

    monkeypatch.setattr("app.services.tutor_runtime.scoring.score_trace", _score_trace)
    monkeypatch.setattr(
        "app.services.tutor_runtime.scoring.score_trace_categorical",
        _score_trace_categorical,
    )

    result = TurnResult(
        turn_id="turn-1",
        tutor_response="ok",
        tutor_question=None,
        action="hint",
        current_step="practice",
        current_step_index=1,
        concept="conduction",
        focus_concepts=["conduction"],
        mastery={"conduction": 0.3},
        mastery_delta={"conduction": 0.1},
        objective_progress={},
        session_complete=False,
        awaiting_evaluation=False,
        step_transition="step:0→1",
        evidence_chunk_ids=["c1", "c2"],
        guard_events=[
            {"name": "guard_override", "guard_name": "forced_advance_max_turns"}
        ],
        decision_requested="CONTINUE_STEP",
        decision_applied="ADVANCE_STEP",
        delegated=True,
        delegation_reason="high_uncertainty",
        delegation_outcome="specialist_path_selected",
        telemetry_contract={
            "version": 4,
            "evidence_count": 2,
            "mastery_delta_abs_sum": 0.1,
            "uncertainty_delta_abs_sum": 0.2,
            "forgetting_risk_delta_sum": 0.0,
        },
    )

    emit_scores("trace-1", result, "student response")

    assert numeric_calls["evidence_count"] == 2.0
    assert numeric_calls["mastery_delta_abs_sum"] == 0.1
    assert numeric_calls["uncertainty_delta_abs_sum"] == 0.2
    assert numeric_calls["forgetting_risk_delta_sum"] == 0.0
    assert numeric_calls["delegation_rate"] == 1.0
    assert numeric_calls["guard_name_count"] == 1.0
    assert categorical_calls["decision_requested"] == "CONTINUE_STEP"
    assert categorical_calls["decision_applied"] == "ADVANCE_STEP"


@pytest.mark.parametrize(
    "module_name",
    [
        "app.services.tutor.turn_pipeline",
        "app.services.tutor.plan_state_adapter",
        "app.services.tutor_runtime.evaluation",
        "app.services.tutor_runtime.runners",
    ],
)
def test_legacy_compatibility_modules_are_disabled(module_name):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)
