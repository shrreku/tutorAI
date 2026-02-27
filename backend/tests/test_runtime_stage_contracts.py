import asyncio
from types import SimpleNamespace

from app.schemas.agent_output import (
    EvaluatorOutput,
    PedagogicalAction,
    PolicyOrchestratorOutput,
    ProgressionDecision,
)
from app.services.tutor_runtime import stage_handoffs
from app.services.tutor_runtime.evaluation_runner import evaluate_response
from app.services.tutor_runtime.types import StageContext


def test_policy_stage_handoff_returns_typed_payload_without_plan_mutation(monkeypatch):
    async def _stub_run_policy(*args, **kwargs):
        return (
            PolicyOrchestratorOutput(
                pedagogical_action=PedagogicalAction.HINT,
                progression_decision=ProgressionDecision.INSERT_AD_HOC,
                confidence=0.7,
                reasoning="insert ad-hoc probe",
                ad_hoc_step_type="probe",
                target_concepts=None,
            ),
            {
                "decision_requested": ProgressionDecision.INSERT_AD_HOC.name,
                "decision_applied": ProgressionDecision.INSERT_AD_HOC.name,
                "reranker_enabled": False,
            },
        )

    monkeypatch.setattr(stage_handoffs, "run_policy", _stub_run_policy)

    plan = {
        "current_step": "explain",
        "current_objective_index": 0,
        "objective_queue": [],
    }
    ctx = StageContext(
        session=SimpleNamespace(),
        plan=plan,
        current_objective={"objective_id": "obj_1"},
        objective_index=0,
        step_index=0,
        student_message="I am confused",
        focus_concepts=["conduction", "temperature", "heat_flux", "energy_balance"],
        mastery_snapshot={"conduction": 0.2},
    )

    result = asyncio.run(
        stage_handoffs.run_policy_stage(
            policy_agent=SimpleNamespace(),
            stage_ctx=ctx,
            evaluation_result=None,
            recent_turns=[],
            max_ad_hoc_default=3,
            lf=None,
        )
    )

    assert result.effective_step_type == "probe"
    assert result.target_concepts == ["conduction", "temperature", "heat_flux"]
    assert result.policy_metadata["decision_requested"] == ProgressionDecision.INSERT_AD_HOC.name
    assert "effective_step_type" not in plan


def test_apply_evaluation_plan_updates_mutates_plan_in_single_place():
    plan = {
        "awaiting_evaluation": True,
        "awaiting_turn_id": "turn-1",
        "objective_progress": {},
    }
    current_obj = {"objective_id": "obj_1"}
    evaluation_result = EvaluatorOutput(
        overall_score=0.9,
        correctness_label="correct",
        multi_concept=False,
    )

    stage_handoffs.apply_evaluation_plan_updates(plan, current_obj, evaluation_result)

    assert plan["awaiting_evaluation"] is False
    assert plan["awaiting_turn_id"] is None
    assert plan["objective_progress"]["obj_1"]["attempts"] == 1
    assert plan["objective_progress"]["obj_1"]["correct"] == 1


def test_evaluation_runner_does_not_mutate_progression_plan_fields():
    class _EvaluatorStub:
        async def evaluate(self, state):
            return EvaluatorOutput(
                overall_score=0.6,
                correctness_label="partial",
                multi_concept=False,
            )

    plan = {
        "current_step": "explain",
        "effective_step_type": "explain",
        "last_tutor_question": "What is conduction?",
        "awaiting_evaluation": True,
        "awaiting_turn_id": "turn-2",
        "objective_progress": {},
    }
    session = SimpleNamespace(mastery={"conduction": 0.2})
    current_obj = {
        "objective_id": "obj_1",
        "concept_scope": {"primary": ["conduction"], "support": [], "prereq": []},
    }

    _evaluation_result, mastery_delta = asyncio.run(
        evaluate_response(
            evaluator_agent=_EvaluatorStub(),
            session=session,
            plan=plan,
            student_message="Conduction is heat transfer through a solid",
            focus_concepts=["conduction"],
            mastery_snap={"conduction": 0.2},
            current_obj=current_obj,
            lf=None,
        )
    )

    assert mastery_delta == {}
    assert plan["awaiting_evaluation"] is True
    assert plan["awaiting_turn_id"] == "turn-2"
    assert plan["objective_progress"] == {}


def test_evaluation_runner_updates_student_concept_state_without_untouched_drift():
    class _EvaluatorStub:
        async def evaluate(self, state):
            return EvaluatorOutput(
                overall_score=0.82,
                correctness_label="correct",
                multi_concept=False,
                concept_deltas={
                    "conduction": {
                        "score": 0.82,
                        "delta": 0.2,
                        "weight": 1.0,
                        "role": "primary",
                    }
                },
            )

    plan = {
        "current_step": "explain",
        "effective_step_type": "explain",
        "last_tutor_question": "What is conduction?",
        "awaiting_evaluation": True,
        "awaiting_turn_id": "turn-3",
        "objective_progress": {},
        "student_concept_state": {
            "conduction": {
                "mastery_mean": 0.2,
                "mastery_uncertainty": 0.7,
                "last_practiced_at": None,
            },
            "convection": {
                "mastery_mean": 0.6,
                "mastery_uncertainty": 0.5,
                "last_practiced_at": None,
            },
        },
    }
    session = SimpleNamespace(mastery={"conduction": 0.2, "convection": 0.6})
    current_obj = {
        "objective_id": "obj_1",
        "concept_scope": {"primary": ["conduction"], "support": [], "prereq": []},
    }

    _evaluation_result, mastery_delta = asyncio.run(
        evaluate_response(
            evaluator_agent=_EvaluatorStub(),
            session=session,
            plan=plan,
            student_message="Conduction is heat transfer through a solid.",
            focus_concepts=["conduction"],
            mastery_snap={"conduction": 0.2},
            current_obj=current_obj,
            lf=None,
        )
    )

    conduction_state = plan["student_concept_state"]["conduction"]
    assert {"mastery_mean", "mastery_uncertainty", "last_practiced_at"}.issubset(conduction_state.keys())
    assert session.mastery["conduction"] == conduction_state["mastery_mean"]
    assert session.mastery["convection"] == 0.6
    assert set(mastery_delta.keys()) == {"conduction"}
    assert plan["awaiting_evaluation"] is True
    assert plan["awaiting_turn_id"] == "turn-3"
    assert plan["objective_progress"] == {}


def test_retrieval_stage_handoff_passes_step_type_and_goal(monkeypatch):
    captured = {}

    async def _stub_retrieve_knowledge(
        retriever,
        session,
        student_message,
        target_concepts,
        step_type,
        step_goal,
        *,
        objective_title=None,
        objective_description=None,
        policy_output=None,
        lf,
    ):
        captured["step_type"] = step_type
        captured["step_goal"] = step_goal
        captured["target_concepts"] = target_concepts
        captured["objective_title"] = objective_title
        captured["objective_description"] = objective_description
        captured["policy_output"] = policy_output
        return [SimpleNamespace(chunk_id="chunk-1", text="example")]

    monkeypatch.setattr(stage_handoffs, "retrieve_knowledge", _stub_retrieve_knowledge)

    ctx = StageContext(
        session=SimpleNamespace(resource_id="r1"),
        plan={"effective_step_type": "practice"},
        current_objective={
            "step_roadmap": [
                {"type": "practice", "goal": "Have the student apply conditional probability."}
            ]
        },
        objective_index=0,
        step_index=0,
        student_message="Can we try a practice problem?",
        focus_concepts=["conditional_probability"],
        mastery_snapshot={"conditional_probability": 0.3},
    )

    result = asyncio.run(
        stage_handoffs.run_retrieval_stage(
            retriever=SimpleNamespace(),
            stage_ctx=ctx,
            target_concepts=["conditional_probability"],
            lf=None,
        )
    )

    assert captured["step_type"] == "practice"
    assert captured["step_goal"] == "Have the student apply conditional probability."
    assert result.evidence_chunk_ids == ["chunk-1"]
