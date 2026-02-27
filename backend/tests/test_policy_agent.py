from app.agents.policy_agent import PolicyAgent
from app.schemas.agent_output import (
    PedagogicalAction,
    PolicyOrchestratorOutput,
    ProgressionDecision,
)
from app.schemas.agent_state import PolicyState


def _make_state(ad_hoc_count: int = 0) -> PolicyState:
    return PolicyState(
        student_message="can we move on?",
        current_step_index=1,
        current_step="practice",
        curriculum_slice={
            "current_objective": {
                "objective_id": "obj_1",
                "step_roadmap": [
                    {"type": "define", "can_skip": True},
                    {"type": "practice", "can_skip": True},
                    {"type": "probe", "can_skip": True},
                    {"type": "assess", "can_skip": False},
                ],
            }
        },
        focus_concepts=["c1", "c2", "c3", "c4"],
        ad_hoc_count=ad_hoc_count,
        max_ad_hoc_per_objective=2,
        current_objective_index=0,
        total_objectives=1,
    )


def test_guard_rejects_invalid_skip_target():
    agent = PolicyAgent()
    state = _make_state()
    out = PolicyOrchestratorOutput(
        pedagogical_action=PedagogicalAction.QUESTION,
        progression_decision=ProgressionDecision.SKIP_TO_STEP,
        skip_target_index=1,
        confidence=0.7,
        reasoning="skip requested",
    )

    guarded = agent._apply_decision_guards(state, out)

    assert guarded.progression_decision == ProgressionDecision.CONTINUE_STEP
    assert guarded.skip_target_index is None


def test_guard_accepts_forward_skippable_skip():
    agent = PolicyAgent()
    state = _make_state()
    out = PolicyOrchestratorOutput(
        pedagogical_action=PedagogicalAction.QUESTION,
        progression_decision=ProgressionDecision.SKIP_TO_STEP,
        skip_target_index=3,
        confidence=0.8,
        reasoning="skip requested",
    )

    guarded = agent._apply_decision_guards(state, out)

    assert guarded.progression_decision == ProgressionDecision.SKIP_TO_STEP
    assert guarded.skip_target_index == 3


def test_guard_forces_advance_when_ad_hoc_budget_exhausted():
    agent = PolicyAgent()
    state = _make_state(ad_hoc_count=2)
    out = PolicyOrchestratorOutput(
        pedagogical_action=PedagogicalAction.HINT,
        progression_decision=ProgressionDecision.INSERT_AD_HOC,
        ad_hoc_step_type="probe",
        confidence=0.6,
        reasoning="insert ad hoc",
    )

    guarded = agent._apply_decision_guards(state, out)

    assert guarded.progression_decision == ProgressionDecision.ADVANCE_STEP
    assert guarded.ad_hoc_step_type is None


def test_guard_infers_student_intent_and_bounds_target_concepts():
    agent = PolicyAgent()
    state = _make_state()
    out = PolicyOrchestratorOutput(
        pedagogical_action=PedagogicalAction.EXPLAIN,
        progression_decision=ProgressionDecision.CONTINUE_STEP,
        confidence=0.6,
        reasoning="continue",
        target_concepts=["a", "b", "c", "d"],
    )

    guarded = agent._apply_decision_guards(state, out)

    assert guarded.student_intent == "move_on"
    assert guarded.progression_decision == ProgressionDecision.ADVANCE_STEP
    assert guarded.target_concepts == ["a", "b", "c"]


def test_guard_move_on_with_low_eval_requires_checkpoint():
    agent = PolicyAgent()
    state = _make_state()
    state.latest_evaluation = {"overall_score": 0.45}
    out = PolicyOrchestratorOutput(
        pedagogical_action=PedagogicalAction.EXPLAIN,
        progression_decision=ProgressionDecision.CONTINUE_STEP,
        confidence=0.6,
        reasoning="continue",
    )

    guarded = agent._apply_decision_guards(state, out)

    assert guarded.student_intent == "move_on"
    assert guarded.progression_decision == ProgressionDecision.CONTINUE_STEP
    assert guarded.recommended_strategy == "assessment"


def test_infer_student_intent_detects_off_topic_and_answer_attempt():
    agent = PolicyAgent()
    off_topic_state = _make_state()
    off_topic_state.student_message = "This is unrelated, whatever."
    answer_attempt_state = _make_state()
    answer_attempt_state.student_message = "I think my answer is 1/2."

    assert agent._infer_student_intent(off_topic_state) == "off_topic"
    assert agent._infer_student_intent(answer_attempt_state) == "answer_attempt"
