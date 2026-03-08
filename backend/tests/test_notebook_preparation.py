import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.services.notebook_preparation import (
    NotebookPreparationService,
    required_capabilities_for_mode,
    resolve_session_scope,
)


class _FakeDb:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


def test_required_capabilities_for_learn_mode_include_resource_profile():
    assert required_capabilities_for_mode("learn") == ["can_answer_doubts", "has_resource_profile"]
    assert required_capabilities_for_mode("practice") == ["can_answer_doubts", "has_resource_profile"]
    assert required_capabilities_for_mode("doubt") == ["can_answer_doubts"]


def test_resolve_session_scope_supports_selected_resources_and_notebook_wide():
    anchor = uuid4()
    second = uuid4()
    third = uuid4()
    active = [anchor, second, third]

    scope_type, resource_ids = resolve_session_scope(anchor, active_resource_ids=active, notebook_wide=True)
    assert scope_type == "notebook"
    assert resource_ids == active

    scope_type, resource_ids = resolve_session_scope(
        anchor,
        active_resource_ids=active,
        selected_resource_ids=[second, third],
    )
    assert scope_type == "selected_resources"
    assert resource_ids[0] == anchor
    assert resource_ids[1:] == [second, third]


def test_prepare_session_context_backfills_missing_profiles_and_returns_summary():
    notebook_id = uuid4()
    user_id = uuid4()
    resource_id = uuid4()
    request = SimpleNamespace(
        resource_id=resource_id,
        selected_resource_ids=[],
        notebook_wide=False,
        selected_topics=["conduction"],
        mode="learn",
        topic="heat transfer",
    )
    resource = SimpleNamespace(
        id=resource_id,
        owner_user_id=user_id,
        filename="heat.pdf",
        topic="physics",
        status="ready",
        processing_profile="core_only",
        capabilities_json={"study_ready": True, "can_answer_doubts": True, "has_resource_profile": False},
    )

    service = NotebookPreparationService(_FakeDb())
    service.notebook_resource_repo = SimpleNamespace(list_active_resource_ids=lambda _notebook_id: asyncio.sleep(0, result=[resource_id]))
    service.resource_repo = SimpleNamespace(get_by_id=lambda _resource_id: asyncio.sleep(0, result=resource))

    async def _ensure_resource_profile(_resource):
        _resource.capabilities_json["has_resource_profile"] = True
        _resource.capabilities_json["resource_profile_ready"] = True
        return 1

    async def _upsert_session_brief(**_kwargs):
        return SimpleNamespace(id=uuid4())

    async def _ensure_topic_prepare(_resource, _request):
        return 1, "learn:conduction"

    service._ensure_resource_profile = _ensure_resource_profile
    service._ensure_topic_prepare = _ensure_topic_prepare
    service._upsert_session_brief = _upsert_session_brief

    summary = asyncio.run(
        service.prepare_session_context(
            notebook_id=notebook_id,
            request=request,
            user_id=user_id,
        )
    )

    assert summary["scope_type"] == "single_resource"
    assert summary["scope_resource_ids"] == [str(resource_id)]
    assert summary["artifacts_created"] == 1
    assert summary["topic_artifacts_created"] == 1
    assert summary["topic_scope_keys"]
    assert summary["resource_profiles_ready"] is True
