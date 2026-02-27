import asyncio
import uuid
from types import SimpleNamespace

from app.agents.evaluator_agent import EvaluatorAgent
from app.agents.safety_critic import SafetyCritic
from app.schemas.agent_output import (
    PedagogicalAction,
    PolicyOrchestratorOutput,
    ProgressionDecision,
    TutorOutput,
)
from app.schemas.agent_state import EvaluatorState
from app.services.llm.openai_provider import OpenAICompatibleProvider
from app.services.retrieval.service import RetrievedChunk
from app.services.tutor_runtime.progression import apply_progression
from app.services.tutor_runtime.response_runner import generate_response


def _make_objective(*, objective_id: str = "obj_1", step_roadmap: list[dict], min_correct: int = 1, min_mastery: float = 0.6) -> dict:
    return {
        "objective_id": objective_id,
        "title": "Heat transfer foundations",
        "concept_scope": {"primary": ["conduction"], "support": [], "prereq": []},
        "step_roadmap": step_roadmap,
        "success_criteria": {
            "min_correct": min_correct,
            "min_mastery": min_mastery,
        },
    }


def _base_plan(current_obj: dict) -> dict:
    return {
        "current_objective_index": 0,
        "current_step_index": 0,
        "current_step": "define",
        "objective_queue": [current_obj],
        "objective_progress": {},
        "ad_hoc_count": 0,
        "max_ad_hoc_per_objective": 3,
        "turns_at_step": 0,
        "step_status": {"0": "active", "1": "upcoming", "2": "upcoming"},
    }


def _policy_output(decision: ProgressionDecision, **kwargs) -> PolicyOrchestratorOutput:
    payload = {
        "pedagogical_action": PedagogicalAction.EXPLAIN,
        "progression_decision": decision,
        "confidence": 0.7,
        "reasoning": "test policy output",
    }
    payload.update(kwargs)
    return PolicyOrchestratorOutput(**payload)


def _session_stub() -> SimpleNamespace:
    return SimpleNamespace(mastery={"conduction": 0.9})


def test_progression_guard_forces_advance_when_ad_hoc_budget_exhausted():
    obj = _make_objective(
        step_roadmap=[
            {"type": "define", "can_skip": True, "max_turns": 3},
            {"type": "practice", "can_skip": True, "max_turns": 3},
            {"type": "assess", "can_skip": False, "max_turns": 3},
        ]
    )
    plan = _base_plan(obj)
    plan["ad_hoc_count"] = 3

    _session_complete, updated_plan, _transition = apply_progression(
        _session_stub(),
        plan,
        _policy_output(ProgressionDecision.INSERT_AD_HOC, ad_hoc_step_type="probe"),
        obj,
        lf=None,
        max_ad_hoc_default=3,
    )

    assert updated_plan["last_decision"] == ProgressionDecision.ADVANCE_STEP.name
    assert updated_plan["ad_hoc_count"] == 0
    guard_events = [e for e in updated_plan.get("__trace_events", []) if e.get("name") == "guard_override"]
    assert any(
        e.get("guard_name") == "forced_return_from_ad_hoc_budget"
        and e.get("decision_requested") == ProgressionDecision.INSERT_AD_HOC.name
        and e.get("decision_applied") == ProgressionDecision.ADVANCE_STEP.name
        for e in guard_events
    )


def test_progression_guard_forces_advance_on_step_turn_limit():
    obj = _make_objective(
        step_roadmap=[
            {"type": "define", "can_skip": True, "max_turns": 2},
            {"type": "practice", "can_skip": True, "max_turns": 3},
            {"type": "assess", "can_skip": False, "max_turns": 3},
        ]
    )
    plan = _base_plan(obj)
    plan["turns_at_step"] = 1

    _session_complete, updated_plan, _transition = apply_progression(
        _session_stub(),
        plan,
        _policy_output(ProgressionDecision.CONTINUE_STEP),
        obj,
        lf=None,
        max_ad_hoc_default=3,
    )

    assert updated_plan["last_decision"] == ProgressionDecision.ADVANCE_STEP.name
    guard_events = [e for e in updated_plan.get("__trace_events", []) if e.get("name") == "guard_override"]
    assert any(
        e.get("guard_name") == "forced_advance_max_turns"
        and e.get("decision_requested") == ProgressionDecision.CONTINUE_STEP.name
        and e.get("decision_applied") == ProgressionDecision.ADVANCE_STEP.name
        for e in guard_events
    )


def test_progression_guard_rejects_invalid_skip_target():
    obj = _make_objective(
        step_roadmap=[
            {"type": "define", "can_skip": True, "max_turns": 3},
            {"type": "practice", "can_skip": False, "max_turns": 3},
            {"type": "assess", "can_skip": False, "max_turns": 3},
        ]
    )
    plan = _base_plan(obj)

    _session_complete, updated_plan, _transition = apply_progression(
        _session_stub(),
        plan,
        _policy_output(ProgressionDecision.SKIP_TO_STEP, skip_target_index=0),
        obj,
        lf=None,
        max_ad_hoc_default=3,
    )

    assert updated_plan["last_decision"] == ProgressionDecision.CONTINUE_STEP.name
    guard_events = [e for e in updated_plan.get("__trace_events", []) if e.get("name") == "guard_override"]
    assert any(
        e.get("guard_name") == "skip_rejected_by_guard"
        and e.get("decision_requested") == ProgressionDecision.SKIP_TO_STEP.name
        and e.get("decision_applied") == ProgressionDecision.CONTINUE_STEP.name
        for e in guard_events
    )


def test_progression_guard_blocks_objective_advance_until_required_steps():
    obj = _make_objective(
        step_roadmap=[
            {"type": "define", "can_skip": True, "max_turns": 3},
            {"type": "practice", "can_skip": True, "max_turns": 3},
            {"type": "assess", "can_skip": False, "max_turns": 3},
        ]
    )
    plan = _base_plan(obj)
    plan["objective_progress"] = {
        "obj_1": {"attempts": 1, "correct": 1, "steps_completed": 0, "steps_skipped": 0}
    }
    plan["step_status"] = {"0": "active", "1": "upcoming", "2": "upcoming"}

    _session_complete, updated_plan, _transition = apply_progression(
        _session_stub(),
        plan,
        _policy_output(ProgressionDecision.ADVANCE_OBJECTIVE),
        obj,
        lf=None,
        max_ad_hoc_default=3,
    )

    assert updated_plan["last_decision"] == ProgressionDecision.ADVANCE_STEP.name
    assert updated_plan["current_step_index"] == 1
    guard_events = [e for e in updated_plan.get("__trace_events", []) if e.get("name") == "guard_override"]
    assert any(
        e.get("guard_name") == "objective_readiness_not_met"
        and e.get("decision_requested") == ProgressionDecision.ADVANCE_OBJECTIVE.name
        and e.get("decision_applied") == ProgressionDecision.ADVANCE_STEP.name
        for e in guard_events
    )


class _TutorStub:
    def __init__(self, output: TutorOutput):
        self.output = output
        self.seen_state = None

    async def generate(self, state):
        self.seen_state = state
        return self.output


def test_response_runner_low_evidence_path_is_explicit_and_traced():
    plan = {"current_step": "explain", "current_step_index": 0}
    tutor_stub = _TutorStub(TutorOutput(response_text="should not be used"))

    result = asyncio.run(
        generate_response(
            tutor_agent=tutor_stub,
            student_message="Can you explain conduction?",
            plan=plan,
            policy_output=_policy_output(ProgressionDecision.CONTINUE_STEP),
            retrieved_chunks=[],
            current_obj={"objective_id": "obj_1", "step_roadmap": []},
            lf=None,
        )
    )

    assert "I want to keep this accurate" in result.response_text
    assert result.evidence_chunk_ids is None
    assert tutor_stub.seen_state is None
    guard_events = [e for e in plan.get("__trace_events", []) if e.get("name") == "guard_override"]
    assert any(e.get("guard_name") == "low_evidence_response_guard" for e in guard_events)


def test_response_runner_backfills_evidence_ids_into_tutor_output():
    plan = {"current_step": "explain", "current_step_index": 0}
    chunk_id = uuid.uuid4()
    retrieved = [
        RetrievedChunk(
            chunk_id=chunk_id,
            text="Conduction is heat transfer through direct molecular interactions.",
            section_heading=None,
            chunk_index=0,
            page_start=None,
            page_end=None,
            pedagogy_role="explanation",
            difficulty=None,
            relevance_score=0.9,
            retrieval_reason="concept match",
        )
    ]
    tutor_stub = _TutorStub(TutorOutput(response_text="Conduction transfers heat through solids."))

    result = asyncio.run(
        generate_response(
            tutor_agent=tutor_stub,
            student_message="Explain conduction.",
            plan=plan,
            policy_output=_policy_output(ProgressionDecision.CONTINUE_STEP),
            retrieved_chunks=retrieved,
            current_obj={"objective_id": "obj_1", "step_roadmap": []},
            lf=None,
        )
    )

    assert result.evidence_chunk_ids == [str(chunk_id)]
    assert tutor_stub.seen_state is not None
    assert tutor_stub.seen_state.evidence_chunk_ids == [str(chunk_id)]


def test_response_runner_prunes_unsupported_cited_evidence_ids():
    plan = {"current_step": "explain", "current_step_index": 0}
    chunk_id = uuid.uuid4()
    retrieved = [
        RetrievedChunk(
            chunk_id=chunk_id,
            text="Conduction is heat transfer through direct molecular interactions.",
            section_heading=None,
            chunk_index=0,
            page_start=None,
            page_end=None,
            pedagogy_role="explanation",
            difficulty=None,
            relevance_score=0.9,
            retrieval_reason="concept match",
        )
    ]
    tutor_stub = _TutorStub(
        TutorOutput(
            response_text="Conduction transfers heat through solids.",
            evidence_chunk_ids=[str(chunk_id), "chunk-unsupported"],
        )
    )

    result = asyncio.run(
        generate_response(
            tutor_agent=tutor_stub,
            student_message="Explain conduction.",
            plan=plan,
            policy_output=_policy_output(ProgressionDecision.CONTINUE_STEP),
            retrieved_chunks=retrieved,
            current_obj={"objective_id": "obj_1", "step_roadmap": []},
            lf=None,
        )
    )

    assert result.evidence_chunk_ids == [str(chunk_id)]
    guard_events = [e for e in plan.get("__trace_events", []) if e.get("name") == "guard_override"]
    assert any(e.get("guard_name") == "unsupported_citation_pruned" for e in guard_events)


class _LLMStub:
    async def generate(self, *args, **kwargs):
        return "{}"


def test_safety_critic_blocks_unsupported_cited_evidence_ids():
    critic = SafetyCritic(_LLMStub())

    result = asyncio.run(
        critic.evaluate(
            response_text="Conduction transfers heat in solids.",
            retrieved_chunks=[{"chunk_id": "chunk-a", "text": "Conduction in solids."}],
            current_objective={"title": "Heat transfer", "concept_scope": {"primary": ["conduction"]}},
            student_message="What is conduction?",
            cited_evidence_chunk_ids=["chunk-missing"],
        )
    )

    assert result.should_block is True
    assert "unsupported_cited_evidence" in result.concerns
    assert result.grounding_assessment == "ungrounded"


def test_evaluator_fallback_is_concept_aware_not_length_only():
    agent = EvaluatorAgent(llm_provider=None)
    base_kwargs = {
        "current_step": "explain",
        "effective_step_type": "explain",
        "current_objective": {"objective_id": "obj_1"},
        "concept_scope": {"primary": ["conduction"], "support": [], "prereq": []},
        "focus_concepts": ["conduction"],
        "mastery_snapshot": {"conduction": 0.2},
    }

    state_with_overlap = EvaluatorState(
        student_message="the conduction mechanism in solids explains heat flow",
        **base_kwargs,
    )
    state_without_overlap = EvaluatorState(
        student_message="the velocity profile in fluids explains heat flow",
        **base_kwargs,
    )

    with_overlap = agent._fallback_evaluation(state_with_overlap)
    without_overlap = agent._fallback_evaluation(state_without_overlap)

    assert with_overlap.overall_score > without_overlap.overall_score
    assert with_overlap.confidence > without_overlap.confidence
    assert "missing_primary_concepts:conduction" in without_overlap.misconceptions


def test_openai_provider_coerces_malformed_policy_and_evaluator_payloads():
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)

    evaluator_payload = {
        "overall_score": 0.6,
        "correctness_label": "PARTIAL",
        "multi_concept": False,
        "concept_deltas": [
            {
                "concept": "conduction",
                "score": 0.7,
                "delta": 0.1,
                "weight": 1.0,
                "role": "primary",
            }
        ],
    }
    coerced_eval = provider._coerce_data(evaluator_payload, schema=type("S", (), {"__name__": "EvaluatorOutput"}))

    policy_payload = {
        "pedagogical_action": "ask",
        "progression_decision": "advance_step",
        "confidence": 0.7,
        "reasoning": "advance now",
        "turn_plan": {"goal": "check understanding", "interaction_type": "custom"},
    }
    coerced_policy = provider._coerce_data(policy_payload, schema=type("S", (), {"__name__": "PolicyOrchestratorOutput"}))

    assert isinstance(coerced_eval["concept_deltas"], dict)
    assert "conduction" in coerced_eval["concept_deltas"]
    assert coerced_eval["correctness_label"] == "partial"
    assert coerced_policy["pedagogical_action"] == "question"
    assert coerced_policy["progression_decision"] == 2
    assert coerced_policy["turn_plan"]["interaction_type"] == "explain_concept"
