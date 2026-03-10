from app.agents.evaluator_agent import EVALUATOR_SYSTEM_PROMPT
from app.agents.policy_agent import POLICY_SYSTEM_PROMPT
from app.agents.safety_critic import SAFETY_SYSTEM_PROMPT
from app.agents.tutor_agent import TUTOR_SYSTEM_PROMPT


FORBIDDEN_LEGACY_TERMS = {
    "phase_skeleton",
    "curriculum_phase_index",
    "intermediate_step_count",
    "max_intermediate_steps",
    "legacy_path_used",
}


def _assert_prompt_has_no_legacy_terms(prompt: str) -> None:
    normalized = prompt.lower()
    for term in FORBIDDEN_LEGACY_TERMS:
        assert term not in normalized, f"Prompt contains legacy term: {term}"


def test_policy_prompt_has_no_legacy_runtime_terms():
    _assert_prompt_has_no_legacy_terms(POLICY_SYSTEM_PROMPT)


def test_tutor_prompt_has_no_legacy_runtime_terms():
    _assert_prompt_has_no_legacy_terms(TUTOR_SYSTEM_PROMPT)


def test_evaluator_prompt_has_no_legacy_runtime_terms():
    _assert_prompt_has_no_legacy_terms(EVALUATOR_SYSTEM_PROMPT)


def test_safety_prompt_has_no_legacy_runtime_terms():
    _assert_prompt_has_no_legacy_terms(SAFETY_SYSTEM_PROMPT)


def test_policy_prompt_mentions_student_intent_controls():
    normalized = POLICY_SYSTEM_PROMPT.lower()
    assert "student_intent" in normalized
    assert "advance_objective" in normalized


def test_policy_prompt_mentions_session_mode_contract():
    normalized = POLICY_SYSTEM_PROMPT.lower()
    assert "session mode contract" in normalized
    assert "practice" in normalized
    assert "revision" in normalized


def test_tutor_prompt_mentions_session_mode_contract():
    normalized = TUTOR_SYSTEM_PROMPT.lower()
    assert "session mode contract" in normalized
    assert "doubt" in normalized
    assert "learn" in normalized


def test_evaluator_prompt_mentions_readiness_contract_fields():
    normalized = EVALUATOR_SYSTEM_PROMPT.lower()
    assert "ready_to_advance" in normalized
    assert "recommended_intervention" in normalized
