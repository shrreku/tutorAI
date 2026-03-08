import asyncio
import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.plan import PlanState
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
        self.commit_count = 0

    def add(self, obj):
        self.added = obj

    async def commit(self):
        self.commit_count += 1
        return None

    async def refresh(self, _obj):
        return None


class _CurriculumStub:
    async def generate_plan(self, resource_id, topic=None, selected_topics=None):
        return {
            "active_topic": topic,
            "objective_queue": [_objective_fixture()],
        }


def test_session_service_writes_new_sessions_as_v3(monkeypatch):
    async def _get_resource(self, resource_id):
        return SimpleNamespace(id=resource_id, topic="heat", status="ready")

    async def _get_or_create_default_user(self):
        return SimpleNamespace(id=uuid.uuid4())

    async def _get_active_session(self, user_id, resource_id):
        return None

    async def _get_concepts(self, resource_id):
        return ["conduction"]

    monkeypatch.setattr(SessionService, "_get_resource", _get_resource)
    monkeypatch.setattr(SessionService, "_get_or_create_default_user", _get_or_create_default_user)
    monkeypatch.setattr(SessionService, "_get_active_session", _get_active_session)
    monkeypatch.setattr(SessionService, "_get_concepts", _get_concepts)

    service = SessionService(_DbStub(), _CurriculumStub())
    session = asyncio.run(service.create_session(resource_id=uuid.uuid4()))

    assert session.plan_state["version"] == 3


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

    async def _get_active_session(self, user_id, resource_id):
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

    async def _get_active_session(self, user_id, resource_id):
        return active_session

    async def _get_concepts(self, resource_id):
        return ["conduction"]

    monkeypatch.setattr(SessionService, "_get_resource", _get_resource)
    monkeypatch.setattr(SessionService, "_get_or_create_default_user", _get_or_create_default_user)
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
