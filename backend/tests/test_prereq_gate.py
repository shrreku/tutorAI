import asyncio
from types import SimpleNamespace

from app.schemas.agent_output import (
    PedagogicalAction,
    PolicyOrchestratorOutput,
    ProgressionDecision,
)
from app.services.tutor_runtime.policy_runner import run_policy
from app.services.tutor_runtime.progression import apply_progression


class _PolicyStub:
    def __init__(self, output: PolicyOrchestratorOutput):
        self._output = output

    async def decide(self, _state):
        return self._output


def test_policy_runner_prereq_gate_steers_retrieval_and_denies_advancement():
    plan = {
        "current_objective_index": 0,
        "current_step_index": 0,
        "current_step": "explain",
        "objective_queue": [
            {
                "objective_id": "obj_1",
                "title": "Advanced topic",
                "concept_scope": {
                    "primary": ["advanced"],
                    "support": [],
                    "prereq": ["set", "function"],
                },
                "step_roadmap": [{"type": "explain", "target_concepts": ["advanced"]}],
                "success_criteria": {"min_correct": 1, "min_mastery": 0.6},
            }
        ],
        "turns_at_step": 0,
        "ad_hoc_count": 0,
        "max_ad_hoc_per_objective": 3,
    }

    current_obj = plan["objective_queue"][0]

    stub = _PolicyStub(
        PolicyOrchestratorOutput(
            pedagogical_action=PedagogicalAction.EXPLAIN,
            progression_decision=ProgressionDecision.ADVANCE_STEP,
            confidence=0.7,
            reasoning="advance",
            target_concepts=["advanced"],
        )
    )

    policy_output, _meta = asyncio.run(
        run_policy(
            policy_agent=stub,
            plan=plan,
            student_message="Can you explain this?",
            focus_concepts=["advanced"],
            mastery_snap={"set": 0.0, "function": 0.0},
            evaluation_result=None,
            current_obj=current_obj,
            recent_turns=[],
            max_ad_hoc_default=3,
            lf=None,
        )
    )

    assert policy_output.progression_decision == ProgressionDecision.CONTINUE_STEP
    assert policy_output.target_concepts == ["set", "function"]
    assert policy_output.retrieval_directives is not None
    assert policy_output.retrieval_directives.get("focus") == "prereq"
    assert "Prereq gate" in (policy_output.planner_guidance or "")

    guard_events = [
        e for e in plan.get("__trace_events", []) if e.get("name") == "guard_override"
    ]
    assert any(e.get("guard_name") == "prereq_gate_not_met" for e in guard_events)


def test_progression_prereq_gate_blocks_advancing_into_next_objective():
    obj_1 = {
        "objective_id": "obj_1",
        "title": "Intro",
        "concept_scope": {"primary": ["conduction"], "support": [], "prereq": []},
        "step_roadmap": [{"type": "define", "can_skip": True, "max_turns": 2}],
        "success_criteria": {"min_correct": 1, "min_mastery": 0.6},
    }
    obj_2 = {
        "objective_id": "obj_2",
        "title": "Next",
        "concept_scope": {
            "primary": ["fourier_law"],
            "support": [],
            "prereq": ["conduction"],
        },
        "step_roadmap": [{"type": "explain", "can_skip": True, "max_turns": 2}],
        "success_criteria": {"min_correct": 1, "min_mastery": 0.6},
    }

    plan = {
        "current_objective_index": 0,
        "current_step_index": 0,
        "current_step": "define",
        "objective_queue": [obj_1, obj_2],
        "objective_progress": {"obj_1": {"attempts": 1, "correct": 1}},
        "ad_hoc_count": 0,
        "max_ad_hoc_per_objective": 3,
        "turns_at_step": 0,
        "step_status": {"0": "active"},
    }

    session = SimpleNamespace(mastery={"conduction": 0.0})

    policy_output = PolicyOrchestratorOutput(
        pedagogical_action=PedagogicalAction.EXPLAIN,
        progression_decision=ProgressionDecision.ADVANCE_STEP,
        confidence=0.7,
        reasoning="advance",
    )

    session_complete, updated_plan, _transition = apply_progression(
        session,
        plan,
        policy_output,
        obj_1,
        lf=None,
        max_ad_hoc_default=3,
    )

    assert session_complete is False
    assert updated_plan["current_objective_index"] == 0
    assert updated_plan["last_decision"] == ProgressionDecision.CONTINUE_STEP.name

    guard_events = [
        e
        for e in updated_plan.get("__trace_events", [])
        if e.get("name") == "guard_override"
    ]
    assert any(e.get("guard_name") == "prereq_gate_not_met" for e in guard_events)
