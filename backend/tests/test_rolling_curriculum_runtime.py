import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.services.tutor_runtime.orchestrator import TurnPipeline


class _CurriculumExtender:
    def __init__(self, new_objectives):
        self.new_objectives = new_objectives
        self.calls = []

    async def extend_plan(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.new_objectives)


def _objective(objective_id: str, concept_id: str) -> dict:
    return {
        "objective_id": objective_id,
        "title": f"Objective {objective_id}",
        "description": f"Learn {concept_id}",
        "concept_scope": {
            "primary": [concept_id],
            "support": [],
            "prereq": [],
        },
        "success_criteria": {"min_correct": 2, "min_mastery": 0.7},
        "estimated_turns": 4,
        "step_roadmap": [
            {
                "type": "define",
                "target_concepts": [concept_id],
                "can_skip": False,
                "max_turns": 2,
                "goal": f"Introduce {concept_id}",
            }
        ],
    }


def test_turn_pipeline_extends_curriculum_horizon_from_scoped_session_scope():
    anchor_resource_id = uuid4()
    second_resource_id = uuid4()
    extender = _CurriculumExtender([_objective("obj_02", "convection")])
    pipeline = TurnPipeline(
        db_session=SimpleNamespace(),
        policy_agent=SimpleNamespace(),
        tutor_agent=SimpleNamespace(llm=None),
        evaluator_agent=SimpleNamespace(),
        safety_critic=SimpleNamespace(),
        retrieval_service=SimpleNamespace(),
        curriculum_agent=extender,
    )
    session = SimpleNamespace(resource_id=anchor_resource_id)
    plan = {
        "mode": "learn",
        "active_topic": "Heat Transfer",
        "current_objective_index": 0,
        "objective_queue": [_objective("obj_01", "conduction")],
        "objective_progress": {
            "obj_01": {
                "attempts": 0,
                "correct": 0,
                "steps_completed": 0,
                "steps_skipped": 0,
            }
        },
        "curriculum_scope": {
            "scope_type": "selected_resources",
            "anchor_resource_id": str(anchor_resource_id),
            "resource_ids": [str(anchor_resource_id), str(second_resource_id)],
            "topic": "Heat Transfer",
            "selected_topics": [],
        },
        "curriculum_planner": {
            "rolling_enabled": True,
            "exhausted": False,
            "extend_when_remaining": 1,
            "objective_batch_size": 2,
            "extension_count": 0,
            "remaining_concepts_estimate": 4,
        },
        "plan_horizon": {
            "version": 1,
            "strategy": "rolling",
            "visible_objectives": 1,
        },
    }

    asyncio.run(
        pipeline._extend_curriculum_horizon_if_needed(
            session=session,
            plan=plan,
        )
    )

    assert len(extender.calls) == 1
    assert extender.calls[0]["scope_resource_ids"] == [
        str(anchor_resource_id),
        str(second_resource_id),
    ]
    assert plan["objective_queue"][-1]["objective_id"] == "obj_02"
    assert plan["objective_progress"]["obj_02"] == {
        "attempts": 0,
        "correct": 0,
        "steps_completed": 0,
        "steps_skipped": 0,
    }
    assert plan["curriculum_planner"]["extension_count"] == 1
    assert plan["last_replan_request"]["reason"] == "rolling_horizon_extended"
    assert plan["plan_horizon"]["visible_objectives"] == 2
