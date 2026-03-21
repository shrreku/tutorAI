import asyncio
import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.plan import PlanState
from app.models.session import TutorTurn
from app.services.tutor.session_service import SessionService
from app.services.tutor_runtime.plan_state_migration import migrate_plan_state_to_v3


def _objective_fixture() -> dict:
    return {
        "objective_id": "obj_1",
        "title": "Understand conduction",
        "description": "Learn heat transfer by conduction.",
        "concept_scope": {
            "primary": ["conduction"],
            "support": [],
            "prereq": [],
        },
        "objective_evidence_chunk_ids_topk": ["chunk_1"],
        "success_criteria": {
            "min_correct": 1,
            "min_mastery": 0.6,
        },
        "estimated_turns": 3,
        "step_roadmap": [
            {
                "type": "explain",
                "target_concepts": ["conduction"],
                "can_skip": False,
                "max_turns": 3,
                "goal": "Explain conduction with a simple example.",
            }
        ],
    }


def _plan_fixture(version: int) -> dict:
    return {
        "version": version,
        "resource_id": str(uuid.uuid4()),
        "objective_queue": [_objective_fixture()],
        "current_objective_index": 0,
        "current_step_index": 0,
        "current_step": "explain",
        "turns_at_step": 0,
        "step_status": {"0": "active"},
        "ad_hoc_count": 0,
        "max_ad_hoc_per_objective": 4,
        "objective_progress": {},
        "focus_concepts": ["conduction"],
    }


def test_plan_state_accepts_v3_only():
    model = PlanState(**_plan_fixture(version=3))
    assert model.version == 3

    with pytest.raises(ValidationError):
        PlanState(**_plan_fixture(version=2))


def test_plan_state_read_migration_upgrades_legacy_version():
    with pytest.raises(ValueError):
        migrate_plan_state_to_v3(_plan_fixture(version=2))


def test_plan_state_read_keeps_v3_runtime_contract():
    migrated = migrate_plan_state_to_v3(_plan_fixture(version=3))
    assert migrated["version"] == 3


class _DbStub:
    def __init__(self):
        self.added = None
        self.added_items = []
        self.commit_count = 0

    def add(self, obj):
        self.added = obj
        self.added_items.append(obj)

    async def commit(self):
        self.commit_count += 1
        return None

    async def refresh(self, _obj):
        return None


class _CurriculumStub:
    async def generate_plan(
        self, resource_id, topic=None, selected_topics=None, mode=None, **kwargs
    ):
        return {
            "active_topic": topic,
            "mode": mode,
            "objective_queue": [_objective_fixture()],
        }


class _CurriculumCountingStub:
    def __init__(self):
        self.calls = 0
        self.last_kwargs = None

    async def generate_plan(
        self, resource_id, topic=None, selected_topics=None, mode=None, **kwargs
    ):
        self.calls += 1
        self.last_kwargs = {
            "resource_id": resource_id,
            "topic": topic,
            "selected_topics": selected_topics,
            "mode": mode,
            **kwargs,
        }
        return {
            "active_topic": topic,
            "mode": mode,
            "objective_queue": [_objective_fixture()],
        }


class _ScalarListResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _ExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _ScalarListResult(self._rows)


def test_session_service_writes_new_sessions_as_v3(monkeypatch):
    async def _get_resource(self, resource_id):
        return SimpleNamespace(id=resource_id, topic="heat", status="ready")

    async def _get_or_create_default_user(self):
        return SimpleNamespace(id=uuid.uuid4())

    async def _get_active_session(self, user_id, resource_id, **_kwargs):
        return None

    async def _get_concepts(self, resource_id):
        return ["conduction"]

    monkeypatch.setattr(SessionService, "_get_resource", _get_resource)
    monkeypatch.setattr(
        SessionService, "_get_or_create_default_user", _get_or_create_default_user
    )
    monkeypatch.setattr(SessionService, "_get_active_session", _get_active_session)
    monkeypatch.setattr(SessionService, "_get_concepts", _get_concepts)

    db = _DbStub()
    service = SessionService(db, _CurriculumStub())
    session = asyncio.run(service.create_session(resource_id=uuid.uuid4()))

    assert session.plan_state["version"] == 3
    assert session.plan_state["mode"] == "learn"
    bootstrap_turns = [item for item in db.added_items if isinstance(item, TutorTurn)]
    assert len(bootstrap_turns) == 1
    assert bootstrap_turns[0].turn_index == 0
    assert bootstrap_turns[0].pedagogical_action == "session_bootstrap"
    assert bootstrap_turns[0].tutor_response


def test_session_service_retires_legacy_active_session(monkeypatch):
    legacy_session = SimpleNamespace(
        id=uuid.uuid4(),
        status="active",
        plan_state={"version": 2},
    )

    async def _get_resource(self, resource_id):
        return SimpleNamespace(id=resource_id, topic="heat", status="ready")

    async def _get_or_create_default_user(self):
        return SimpleNamespace(id=uuid.uuid4())

    async def _get_active_session(self, user_id, resource_id, **_kwargs):
        return legacy_session

    async def _get_concepts(self, resource_id):
        return ["conduction"]

    monkeypatch.setattr(SessionService, "_get_resource", _get_resource)
    monkeypatch.setattr(
        SessionService,
        "_get_or_create_default_user",
        _get_or_create_default_user,
    )
    monkeypatch.setattr(SessionService, "_get_active_session", _get_active_session)
    monkeypatch.setattr(SessionService, "_get_concepts", _get_concepts)

    db = _DbStub()
    service = SessionService(db, _CurriculumStub())
    session = asyncio.run(service.create_session(resource_id=uuid.uuid4()))

    assert legacy_session.status == "completed"
    assert session.plan_state["version"] == 3
    assert db.commit_count == 2


def test_session_service_can_force_new_session_without_resuming(monkeypatch):
    active_session = SimpleNamespace(
        id=uuid.uuid4(),
        status="active",
        plan_state={"version": 3},
    )

    async def _get_resource(self, resource_id):
        return SimpleNamespace(id=resource_id, topic="heat", status="ready")

    async def _get_or_create_default_user(self):
        return SimpleNamespace(id=uuid.uuid4())

    async def _get_active_session(self, user_id, resource_id, **_kwargs):
        return active_session

    async def _get_concepts(self, resource_id):
        return ["conduction"]

    monkeypatch.setattr(SessionService, "_get_resource", _get_resource)
    monkeypatch.setattr(
        SessionService, "_get_or_create_default_user", _get_or_create_default_user
    )
    monkeypatch.setattr(SessionService, "_get_active_session", _get_active_session)
    monkeypatch.setattr(SessionService, "_get_concepts", _get_concepts)

    db = _DbStub()
    service = SessionService(db, _CurriculumStub())
    session = asyncio.run(
        service.create_session(
            resource_id=uuid.uuid4(),
            resume_existing=False,
        )
    )

    assert session is not active_session
    assert session.plan_state["version"] == 3


def test_get_active_session_uses_newest_when_duplicates_exist():
    resource_id = uuid.uuid4()
    newest = SimpleNamespace(
        id=uuid.uuid4(),
        status="active",
        plan_state={
            "curriculum_scope": {
                "scope_type": "single_resource",
                "resource_ids": [],
            }
        },
        resource_id=resource_id,
    )
    older = SimpleNamespace(
        id=uuid.uuid4(),
        status="active",
        plan_state={
            "curriculum_scope": {
                "scope_type": "single_resource",
                "resource_ids": [],
            }
        },
        resource_id=uuid.uuid4(),
    )

    class _DbExecuteStub:
        async def execute(self, _query):
            return _ExecuteResult([newest, older])

    service = SessionService(_DbExecuteStub(), _CurriculumStub())
    session = asyncio.run(service._get_active_session(uuid.uuid4(), resource_id))

    assert session is newest


def test_session_service_bootstraps_first_step_from_mode_contract(monkeypatch):
    async def _get_resource(self, resource_id):
        return SimpleNamespace(id=resource_id, topic="heat", status="ready")

    async def _get_or_create_default_user(self):
        return SimpleNamespace(id=uuid.uuid4())

    async def _get_active_session(self, user_id, resource_id, **_kwargs):
        return None

    async def _get_concepts(self, resource_id):
        return ["conduction"]

    monkeypatch.setattr(SessionService, "_get_resource", _get_resource)
    monkeypatch.setattr(
        SessionService, "_get_or_create_default_user", _get_or_create_default_user
    )
    monkeypatch.setattr(SessionService, "_get_active_session", _get_active_session)
    monkeypatch.setattr(SessionService, "_get_concepts", _get_concepts)

    service = SessionService(_DbStub(), _CurriculumStub())
    session = asyncio.run(
        service.create_session(
            resource_id=uuid.uuid4(),
            mode="learn",
        )
    )

    roadmap = session.plan_state["objective_queue"][0]["step_roadmap"]
    assert roadmap[0]["type"] == "motivate"
    assert session.plan_state["current_step"] == "motivate"
    assert session.plan_state["step_status"] == {"0": "active", "1": "upcoming"}


def test_session_service_fails_early_when_ready_resource_has_no_concepts(monkeypatch):
    async def _get_resource(self, resource_id):
        return SimpleNamespace(id=resource_id, topic="heat", status="ready")

    async def _get_or_create_default_user(self):
        return SimpleNamespace(id=uuid.uuid4())

    async def _get_active_session(self, user_id, resource_id, **_kwargs):
        return None

    async def _get_concepts(self, resource_id):
        return []

    monkeypatch.setattr(SessionService, "_get_resource", _get_resource)
    monkeypatch.setattr(
        SessionService, "_get_or_create_default_user", _get_or_create_default_user
    )
    monkeypatch.setattr(SessionService, "_get_active_session", _get_active_session)
    monkeypatch.setattr(SessionService, "_get_concepts", _get_concepts)

    curriculum = _CurriculumCountingStub()
    service = SessionService(_DbStub(), curriculum)

    with pytest.raises(ValueError, match="has no admitted concepts yet"):
        asyncio.run(service.create_session(resource_id=uuid.uuid4(), mode="learn"))

    assert curriculum.calls == 0


def test_session_service_allows_doubt_mode_without_concepts(monkeypatch):
    async def _get_resource(self, resource_id):
        return SimpleNamespace(id=resource_id, topic="heat", status="ready")

    async def _get_or_create_default_user(self):
        return SimpleNamespace(id=uuid.uuid4())

    async def _get_active_session(self, user_id, resource_id, **_kwargs):
        return None

    async def _get_concepts(self, resource_id):
        return []

    monkeypatch.setattr(SessionService, "_get_resource", _get_resource)
    monkeypatch.setattr(
        SessionService, "_get_or_create_default_user", _get_or_create_default_user
    )
    monkeypatch.setattr(SessionService, "_get_active_session", _get_active_session)
    monkeypatch.setattr(SessionService, "_get_concepts", _get_concepts)

    curriculum = _CurriculumCountingStub()
    service = SessionService(_DbStub(), curriculum)
    session = asyncio.run(
        service.create_session(resource_id=uuid.uuid4(), mode="doubt")
    )

    assert curriculum.calls == 0
    assert session.plan_state["mode"] == "doubt"
    assert (
        session.plan_state["objective_queue"][0]["objective_id"] == "obj_doubt_clarify"
    )
    assert session.plan_state["current_step"] == "clarify"


def test_session_service_uses_scoped_curriculum_source_and_seeds_rolling_planner(monkeypatch):
    anchor_resource_id = uuid.uuid4()
    second_resource_id = uuid.uuid4()

    async def _get_resource(self, resource_id):
        return SimpleNamespace(id=resource_id, topic="heat", status="ready")

    async def _get_or_create_default_user(self):
        return SimpleNamespace(id=uuid.uuid4())

    async def _get_active_session(self, user_id, resource_id, **_kwargs):
        return None

    async def _get_scope_concepts(self, resource_ids):
        assert resource_ids == [str(anchor_resource_id), str(second_resource_id)]
        return [
            "conduction",
            "convection",
            "radiation",
            "heat_flux",
            "thermal_equilibrium",
            "boundary_layer",
            "entropy",
        ]

    monkeypatch.setattr(SessionService, "_get_resource", _get_resource)
    monkeypatch.setattr(
        SessionService, "_get_or_create_default_user", _get_or_create_default_user
    )
    monkeypatch.setattr(SessionService, "_get_active_session", _get_active_session)
    monkeypatch.setattr(SessionService, "_get_scope_concepts", _get_scope_concepts)

    curriculum = _CurriculumCountingStub()
    service = SessionService(_DbStub(), curriculum)
    session = asyncio.run(
        service.create_session(
            resource_id=anchor_resource_id,
            scope_type="selected_resources",
            scope_resource_ids=[str(anchor_resource_id), str(second_resource_id)],
            notebook_id=str(uuid.uuid4()),
            mode="learn",
        )
    )

    assert curriculum.calls == 1
    assert curriculum.last_kwargs["scope_resource_ids"] == [
        str(anchor_resource_id),
        str(second_resource_id),
    ]
    assert curriculum.last_kwargs["scope_type"] == "selected_resources"
    assert curriculum.last_kwargs["objective_limit"] == 3
    assert session.plan_state["curriculum_scope"]["resource_ids"] == [
        str(anchor_resource_id),
        str(second_resource_id),
    ]
    assert session.plan_state["plan_horizon"]["strategy"] == "rolling"
    assert session.plan_state["curriculum_planner"]["rolling_enabled"] is True
