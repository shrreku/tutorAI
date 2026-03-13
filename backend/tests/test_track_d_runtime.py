import uuid
from types import SimpleNamespace

from app.schemas.agent_output import (
    PedagogicalAction,
    PolicyOrchestratorOutput,
    ProgressionDecision,
)
from app.services.policy_replay import (
    build_policy_replay_row,
    summarize_policy_replay,
)
from app.services.tutor_runtime.persistence import _serialize_policy_output
from app.services.tutor_runtime.delegation import decide_adaptive_delegation
from app.services.tutor_runtime.policy_reranker import rerank_policy_output


def _policy_output(decision: ProgressionDecision) -> PolicyOrchestratorOutput:
    return PolicyOrchestratorOutput(
        pedagogical_action=PedagogicalAction.EXPLAIN,
        progression_decision=decision,
        confidence=0.8,
        reasoning="policy test",
    )


def test_policy_reranker_respects_feature_flag(monkeypatch):
    from app.services.tutor_runtime import policy_reranker

    monkeypatch.setattr(policy_reranker.settings, "LLM_RERANKER_ENABLED", False)
    result = rerank_policy_output(
        _policy_output(ProgressionDecision.CONTINUE_STEP),
        plan={"turns_at_step": 0},
        evaluation_result={
            "overall_score": 0.95,
            "correctness_label": "correct",
            "uncertainty": 0.1,
        },
    )

    assert result.enabled is False
    assert result.changed is False
    assert result.applied_decision == ProgressionDecision.CONTINUE_STEP.name


def test_policy_reranker_can_change_decision_when_enabled(monkeypatch):
    from app.services.tutor_runtime import policy_reranker

    monkeypatch.setattr(policy_reranker.settings, "LLM_RERANKER_ENABLED", True)
    result = rerank_policy_output(
        _policy_output(ProgressionDecision.CONTINUE_STEP),
        plan={"turns_at_step": 0},
        evaluation_result={
            "overall_score": 0.2,
            "correctness_label": "incorrect",
            "uncertainty": 0.85,
        },
    )

    assert result.enabled is True
    assert result.changed is True
    assert result.applied_decision == ProgressionDecision.INSERT_AD_HOC.name


def test_adaptive_delegation_triggers_on_repeated_confusion_and_is_bounded(monkeypatch):
    from app.services.tutor_runtime import delegation

    monkeypatch.setattr(delegation.settings, "ADAPTIVE_DELEGATION_ENABLED", True)

    plan = {
        "delegation_cooldown_turns": 0,
        "student_concept_state": {
            "conduction": {
                "mastery_mean": 0.2,
                "mastery_uncertainty": 0.8,
                "last_practiced_at": None,
            }
        },
    }
    recent_turns = [
        {"evaluator_output": {"label": "incorrect"}},
        {"evaluator_output": {"label": "unclear"}},
    ]

    first = decide_adaptive_delegation(
        plan=plan,
        recent_turns=recent_turns,
        evaluation_result={"correctness_label": "incorrect"},
        focus_concepts=["conduction"],
        retrieved_chunks=[SimpleNamespace(chunk_id=uuid.uuid4())],
        evidence_chunk_ids=[],
    )
    second = decide_adaptive_delegation(
        plan=plan,
        recent_turns=recent_turns,
        evaluation_result={"correctness_label": "incorrect"},
        focus_concepts=["conduction"],
        retrieved_chunks=[SimpleNamespace(chunk_id=uuid.uuid4())],
        evidence_chunk_ids=[],
    )

    assert first.delegated is True
    assert first.reason == "repeated_confusion"
    assert second.delegated is False
    assert second.outcome == "cooldown_active"


def test_policy_replay_row_contains_track_d_fields():
    turn = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        turn_index=4,
        current_step="practice",
        current_step_index=1,
        target_concepts=["conduction"],
        mastery_before={"conduction": 0.2},
        mastery_after={"conduction": 0.3},
        policy_output={
            "action": "hint",
            "decision_requested": "CONTINUE_STEP",
            "decision_applied": "ADVANCE_STEP",
            "student_intent": "move_on",
            "guard_override_labels": ["forced_advance_max_turns"],
            "delegated": True,
            "delegation_reason": "high_uncertainty",
            "delegation_outcome": "specialist_path_selected",
            "objective_id": "obj_1",
        },
        evaluator_output={"score": 0.7, "label": "partial"},
        retrieved_chunks=[
            {"chunk_id": "c1", "is_cited_evidence": True},
            {"chunk_id": "c2", "is_cited_evidence": False},
        ],
        pedagogical_action="hint",
        rl_reward=0.6,
    )

    row = build_policy_replay_row(turn)

    assert row["decision_requested"] == "CONTINUE_STEP"
    assert row["decision_applied"] == "ADVANCE_STEP"
    assert row["student_intent"] == "move_on"
    assert row["guard_override_labels"] == ["forced_advance_max_turns"]
    assert row["evidence_metrics"]["coverage"] == 0.5
    assert row["delegation"]["delegated"] is True

    summary = summarize_policy_replay([row])
    assert summary["guard_override_rate"] == 1.0
    assert summary["delegation_rate"] == 1.0
    assert summary["decision_alignment_rate"] == 0.0


def test_serialize_policy_output_persists_student_intent():
    output = _serialize_policy_output(
        _policy_output(ProgressionDecision.CONTINUE_STEP),
        policy_metadata={"student_intent": "move_on"},
    )

    assert output["student_intent"] == "move_on"
