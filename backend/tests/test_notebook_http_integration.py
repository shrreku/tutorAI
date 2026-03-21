from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.api.v1 import notebooks as notebooks_module
from app.api.v1 import sessions as sessions_module
from app.api.v1 import tutor as tutor_module
from app.db.database import get_db


class _DummyDb:
    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


async def _dummy_db_dep():
    yield _DummyDb()


def _build_client():
    app.dependency_overrides[get_db] = _dummy_db_dep
    return TestClient(app)


def test_http_notebooks_list_returns_paginated_payload(monkeypatch):
    user_id = uuid4()

    class _Repo:
        def __init__(self, _db):
            pass

        async def get_by_student(self, _student_id, status=None, limit=50, offset=0):
            return [
                SimpleNamespace(
                    id=uuid4(),
                    student_id=user_id,
                    title="Physics Notebook",
                    goal="Prepare for exam",
                    target_date=None,
                    status="active",
                    settings_json={"default_mode": "learn"},
                    created_at="2026-03-04T00:00:00Z",
                    updated_at="2026-03-04T00:00:00Z",
                )
            ]

        async def count_by_student(self, _student_id, status=None):
            return 1

    async def _fake_user():
        return SimpleNamespace(id=user_id)

    monkeypatch.setattr(notebooks_module, "NotebookRepository", _Repo)
    app.dependency_overrides[notebooks_module.require_auth] = _fake_user

    with _build_client() as client:
        response = client.get("/api/v1/notebooks")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "Physics Notebook"

    app.dependency_overrides.clear()


def test_http_notebook_artifact_generate_rejects_unsupported_type(monkeypatch):
    async def _fake_user():
        return SimpleNamespace(id=uuid4())

    async def _fake_owner(*_args, **_kwargs):
        return SimpleNamespace(id=uuid4())

    app.dependency_overrides[notebooks_module.require_auth] = _fake_user
    monkeypatch.setattr(notebooks_module, "verify_notebook_owner", _fake_owner)

    with _build_client() as client:
        response = client.post(
            f"/api/v1/notebooks/{uuid4()}/artifacts:generate",
            json={"artifact_type": "mind_map"},
        )

    assert response.status_code == 400
    assert "Unsupported artifact_type" in response.json()["detail"]

    app.dependency_overrides.clear()


def test_http_notebook_tutor_turn_requires_notebook_session_mapping(monkeypatch):
    user_id = uuid4()
    session_id = uuid4()

    async def _fake_user():
        return SimpleNamespace(id=user_id)

    async def _fake_verify_session_owner(*_args, **_kwargs):
        return None

    async def _fake_verify_notebook_session_link(*_args, **_kwargs):
        raise HTTPException(
            status_code=404, detail="Notebook session mapping not found"
        )

    class _SessionRepo:
        def __init__(self, _db):
            pass

        async def get_by_id(self, _session_id):
            return SimpleNamespace(id=session_id, user_id=user_id, status="active")

    class _NotebookResourceRepo:
        def __init__(self, _db):
            pass

        async def list_active_resource_ids(self, _notebook_id):
            return []

    app.dependency_overrides[tutor_module.check_rate_limit] = _fake_user
    app.dependency_overrides[tutor_module.get_byok_api_key] = lambda: {
        "api_key": None,
        "api_base_url": None,
    }
    monkeypatch.setattr(
        tutor_module, "verify_session_owner", _fake_verify_session_owner
    )
    monkeypatch.setattr(
        tutor_module, "verify_notebook_session_link", _fake_verify_notebook_session_link
    )
    monkeypatch.setattr(tutor_module, "SessionRepository", _SessionRepo)
    monkeypatch.setattr(
        tutor_module, "NotebookResourceRepository", _NotebookResourceRepo
    )

    with _build_client() as client:
        response = client.post(
            f"/api/v1/tutor/notebooks/{uuid4()}/turn",
            json={"session_id": str(session_id), "message": "hello"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Notebook session mapping not found"

    app.dependency_overrides.clear()


def test_http_legacy_session_create_endpoint_gone_when_notebooks_enabled(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_NOTEBOOKS_ENABLED", True, raising=False)

    async def _fake_user():
        return SimpleNamespace(id=uuid4())

    app.dependency_overrides[sessions_module.require_auth] = _fake_user

    with _build_client() as client:
        response = client.post(
            "/api/v1/sessions/resource",
            json={"resource_id": str(uuid4())},
        )

    assert response.status_code == 410
    assert "removed" in response.json()["detail"]
    app.dependency_overrides.clear()


def test_http_legacy_tutor_turn_endpoint_gone_when_notebooks_enabled(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_NOTEBOOKS_ENABLED", True, raising=False)

    async def _fake_user():
        return SimpleNamespace(id=uuid4())

    app.dependency_overrides[tutor_module.check_rate_limit] = _fake_user
    app.dependency_overrides[tutor_module.get_byok_api_key] = lambda: {
        "api_key": None,
        "api_base_url": None,
    }

    with _build_client() as client:
        response = client.post(
            "/api/v1/tutor/turn",
            json={"session_id": str(uuid4()), "message": "hello"},
        )

    assert response.status_code == 410
    assert "removed" in response.json()["detail"]
    app.dependency_overrides.clear()


def test_http_notebook_session_creation_returns_preparation_summary(monkeypatch):
    user_id = uuid4()
    notebook_id = uuid4()
    resource_id = uuid4()
    session_id = uuid4()

    monkeypatch.setattr(settings, "OPERATION_METERING_ENABLED", False, raising=False)

    async def _fake_user():
        return SimpleNamespace(id=user_id)

    async def _fake_owner(*_args, **_kwargs):
        return SimpleNamespace(id=notebook_id)

    class _NotebookResourceRepo:
        def __init__(self, _db):
            pass

        async def get_by_pair(self, _notebook_id, _resource_id):
            return SimpleNamespace(notebook_id=notebook_id, resource_id=resource_id)

    class _ResourceRepo:
        def __init__(self, _db):
            pass

        async def get_by_id(self, _resource_id):
            return SimpleNamespace(
                id=resource_id,
                owner_user_id=user_id,
                filename="chapter-2.pdf",
                capabilities_json={
                    "curriculum_ready": False,
                    "has_topic_bundles": False,
                },
                file_path_or_uri=None,
            )

    class _NotebookSessionRepo:
        def __init__(self, _db):
            pass

        async def get_by_pair(self, _notebook_id, _session_id):
            return None

        async def create(self, notebook_session):
            notebook_session.id = uuid4()
            notebook_session.started_at = "2026-03-08T00:00:00Z"
            notebook_session.ended_at = None
            notebook_session.created_at = "2026-03-08T00:00:00Z"
            notebook_session.updated_at = "2026-03-08T00:00:00Z"
            return notebook_session

    class _UserRepo:
        def __init__(self, _db):
            pass

        async def get_global_consent(self, _user):
            return (False, None)

    class _PreparationService:
        def __init__(self, _db):
            pass

        async def prepare_session_context(self, *, notebook_id, request, user_id):
            assert notebook_id
            assert request.resource_id == resource_id
            assert user_id
            return {
                "scope_type": "selected_resources",
                "scope_resource_ids": [str(resource_id)],
                "required_capabilities": ["can_answer_doubts", "has_resource_profile"],
                "artifacts_created": 1,
                "resource_profiles_ready": True,
                "session_brief_artifact_id": str(uuid4()),
            }

    class _BatchedCurriculumPreparationService:
        def __init__(self, _db, **_kwargs):
            pass

        async def ensure_curriculum_ready(self, _resource_id):
            assert _resource_id == resource_id
            return {
                "prepared": True,
                "concepts_admitted": 4,
                "topic_bundles": 2,
            }

    class _CreditMeter:
        def __init__(self, _db):
            pass

        def estimate_curriculum_preparation_v2(self, **_kwargs):
            return {"estimated_credits_low": 1, "estimated_credits_high": 2}

        async def create_operation(self, *_args, **_kwargs):
            return SimpleNamespace(id=uuid4())

        async def reserve_operation(self, *_args, **_kwargs):
            return 2

        async def append_usage_line(self, *_args, **_kwargs):
            return None

        async def finalize_operation(self, *_args, **_kwargs):
            return 2

        async def release_operation(self, *_args, **_kwargs):
            return None

    class _SessionService:
        def __init__(self, _db, _curriculum_agent):
            pass

        async def create_session(self, **_kwargs):
            return SimpleNamespace(
                id=session_id,
                user_id=user_id,
                resource_id=resource_id,
                status="active",
                consent_training=False,
                mastery=None,
                plan_state={},
                created_at="2026-03-08T00:00:00Z",
            )

    class _IngestionRepo:
        def __init__(self, _db):
            pass

        async def get_by_resource(self, _resource_id):
            return None

    monkeypatch.setattr(
        notebooks_module, "NotebookResourceRepository", _NotebookResourceRepo
    )
    monkeypatch.setattr(notebooks_module, "ResourceRepository", _ResourceRepo)
    monkeypatch.setattr(
        notebooks_module, "NotebookSessionRepository", _NotebookSessionRepo
    )
    monkeypatch.setattr(notebooks_module, "UserProfileRepository", _UserRepo)
    monkeypatch.setattr(
        notebooks_module, "NotebookPreparationService", _PreparationService
    )
    monkeypatch.setattr(
        notebooks_module, "BatchedCurriculumPreparationService", _BatchedCurriculumPreparationService
    )
    monkeypatch.setattr(notebooks_module, "CreditMeter", _CreditMeter)
    monkeypatch.setattr(notebooks_module, "IngestionJobRepository", _IngestionRepo)
    monkeypatch.setattr(notebooks_module, "SessionService", _SessionService)
    monkeypatch.setattr(
        notebooks_module, "CurriculumAgent", lambda *_args, **_kwargs: SimpleNamespace()
    )
    monkeypatch.setattr(
        notebooks_module,
        "create_embedding_provider",
        lambda *_args, **_kwargs: SimpleNamespace(embed=lambda *_a, **_k: []),
    )
    monkeypatch.setattr(
        notebooks_module,
        "create_llm_provider",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        notebooks_module,
        "create_llm_provider",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(notebooks_module, "verify_notebook_owner", _fake_owner)
    monkeypatch.setattr(
        notebooks_module, "emit_notebook_event", lambda *_args, **_kwargs: None
    )
    app.dependency_overrides[notebooks_module.require_auth] = _fake_user
    app.dependency_overrides[notebooks_module.get_byok_api_key] = lambda: {
        "api_key": None,
        "api_base_url": None,
    }

    with _build_client() as client:
        response = client.post(
            f"/api/v1/notebooks/{notebook_id}/sessions",
            json={
                "resource_id": str(resource_id),
                "mode": "learn",
                "selected_resource_ids": [str(resource_id)],
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["preparation_summary"]["scope_type"] == "selected_resources"
    assert payload["preparation_summary"]["artifacts_created"] == 1
    assert payload["preparation_summary"]["curriculum_preparation"]["prepared"] is True

    app.dependency_overrides.clear()


def test_http_notebook_resources_include_resource_snapshot(monkeypatch):
    user_id = uuid4()
    notebook_id = uuid4()
    resource_id = uuid4()
    link_id = uuid4()

    async def _fake_user():
        return SimpleNamespace(id=user_id)

    async def _fake_owner(*_args, **_kwargs):
        return SimpleNamespace(id=notebook_id)

    class _NotebookResourceRepo:
        def __init__(self, _db):
            pass

        async def get_by_notebook(self, _notebook_id):
            return [
                SimpleNamespace(
                    id=link_id,
                    notebook_id=notebook_id,
                    resource_id=resource_id,
                    role="supplemental",
                    is_active=True,
                    added_at="2026-03-12T00:00:00Z",
                    created_at="2026-03-12T00:00:00Z",
                    updated_at="2026-03-12T00:00:00Z",
                )
            ]

    class _ResourceRepo:
        def __init__(self, _db):
            pass

        async def get_by_ids(self, resource_ids, owner_user_id=None):
            assert resource_ids == [resource_id]
            assert owner_user_id == user_id
            return [
                SimpleNamespace(
                    id=resource_id,
                    filename="chapter-2.pdf",
                    topic="Mechanics",
                    status="ready",
                    processing_profile="prepared_for_curriculum",
                    capabilities_json={
                        "curriculum_ready": True,
                        "has_topic_bundles": True,
                    },
                    uploaded_at="2026-03-12T00:00:00Z",
                    processed_at="2026-03-12T00:10:00Z",
                    processed=True,
                )
            ]

    class _IngestionRepo:
        def __init__(self, _db):
            pass

        async def get_latest_by_resource_ids(self, resource_ids):
            assert resource_ids == [resource_id]
            return {}

    monkeypatch.setattr(
        notebooks_module, "NotebookResourceRepository", _NotebookResourceRepo
    )
    monkeypatch.setattr(notebooks_module, "ResourceRepository", _ResourceRepo)
    monkeypatch.setattr(notebooks_module, "IngestionJobRepository", _IngestionRepo)
    monkeypatch.setattr(notebooks_module, "verify_notebook_owner", _fake_owner)
    app.dependency_overrides[notebooks_module.require_auth] = _fake_user

    with _build_client() as client:
        response = client.get(f"/api/v1/notebooks/{notebook_id}/resources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["resource"]["filename"] == "chapter-2.pdf"
    assert payload["items"][0]["resource"]["capabilities"]["curriculum_ready"] is True

    app.dependency_overrides.clear()


def test_http_notebook_session_creation_runs_curriculum_before_preparation(monkeypatch):
    user_id = uuid4()
    notebook_id = uuid4()
    resource_id = uuid4()
    session_id = uuid4()
    calls = {"curriculum": 0}

    monkeypatch.setattr(settings, "OPERATION_METERING_ENABLED", False, raising=False)

    async def _fake_user():
        return SimpleNamespace(id=user_id)

    async def _fake_owner(*_args, **_kwargs):
        return SimpleNamespace(id=notebook_id)

    class _NotebookResourceRepo:
        def __init__(self, _db):
            pass

        async def get_by_pair(self, _notebook_id, _resource_id):
            return SimpleNamespace(notebook_id=notebook_id, resource_id=resource_id)

    class _ResourceRepo:
        def __init__(self, _db):
            pass

        async def get_by_id(self, _resource_id):
            return SimpleNamespace(
                id=resource_id,
                owner_user_id=user_id,
                filename="chapter-2.pdf",
                capabilities_json={
                    "curriculum_ready": False,
                    "has_topic_bundles": False,
                },
                file_path_or_uri=None,
            )

    class _NotebookSessionRepo:
        def __init__(self, _db):
            pass

        async def get_by_pair(self, _notebook_id, _session_id):
            return None

        async def create(self, notebook_session):
            notebook_session.id = uuid4()
            notebook_session.started_at = "2026-03-08T00:00:00Z"
            notebook_session.ended_at = None
            notebook_session.created_at = "2026-03-08T00:00:00Z"
            notebook_session.updated_at = "2026-03-08T00:00:00Z"
            return notebook_session

    class _UserRepo:
        def __init__(self, _db):
            pass

        async def get_global_consent(self, _user):
            return (False, None)

    class _PreparationService:
        def __init__(self, _db):
            pass

        async def prepare_session_context(self, **_kwargs):
            assert calls["curriculum"] == 1
            return {
                "scope_type": "single_resource",
                "scope_resource_ids": [str(resource_id)],
            }

    class _BatchedCurriculumPreparationService:
        def __init__(self, _db, **_kwargs):
            pass

        async def ensure_curriculum_ready(self, _resource_id):
            calls["curriculum"] += 1
            return {"prepared": True, "concepts_admitted": 2}

    class _CreditMeter:
        def __init__(self, _db):
            pass

        def estimate_curriculum_preparation_v2(self, **_kwargs):
            return {"estimated_credits_low": 1, "estimated_credits_high": 2}

        async def create_operation(self, *_args, **_kwargs):
            return SimpleNamespace(id=uuid4())

        async def reserve_operation(self, *_args, **_kwargs):
            return 2

        async def append_usage_line(self, *_args, **_kwargs):
            return None

        async def finalize_operation(self, *_args, **_kwargs):
            return 2

        async def release_operation(self, *_args, **_kwargs):
            return None

    class _SessionService:
        def __init__(self, _db, _curriculum_agent):
            pass

        async def create_session(self, **_kwargs):
            return SimpleNamespace(
                id=session_id,
                user_id=user_id,
                resource_id=resource_id,
                status="active",
                consent_training=False,
                mastery=None,
                plan_state={},
                created_at="2026-03-08T00:00:00Z",
            )

    class _IngestionRepo:
        def __init__(self, _db):
            pass

        async def get_by_resource(self, _resource_id):
            return None

    monkeypatch.setattr(
        notebooks_module, "NotebookResourceRepository", _NotebookResourceRepo
    )
    monkeypatch.setattr(notebooks_module, "ResourceRepository", _ResourceRepo)
    monkeypatch.setattr(
        notebooks_module, "NotebookSessionRepository", _NotebookSessionRepo
    )
    monkeypatch.setattr(notebooks_module, "UserProfileRepository", _UserRepo)
    monkeypatch.setattr(
        notebooks_module, "NotebookPreparationService", _PreparationService
    )
    monkeypatch.setattr(
        notebooks_module, "BatchedCurriculumPreparationService", _BatchedCurriculumPreparationService
    )
    monkeypatch.setattr(notebooks_module, "CreditMeter", _CreditMeter)
    monkeypatch.setattr(notebooks_module, "IngestionJobRepository", _IngestionRepo)
    monkeypatch.setattr(notebooks_module, "SessionService", _SessionService)
    monkeypatch.setattr(
        notebooks_module, "CurriculumAgent", lambda *_args, **_kwargs: SimpleNamespace()
    )
    monkeypatch.setattr(notebooks_module, "verify_notebook_owner", _fake_owner)
    monkeypatch.setattr(
        notebooks_module, "emit_notebook_event", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        notebooks_module,
        "create_embedding_provider",
        lambda *_args, **_kwargs: SimpleNamespace(embed=lambda *_a, **_k: []),
    )
    monkeypatch.setattr(
        notebooks_module,
        "create_llm_provider",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    app.dependency_overrides[notebooks_module.require_auth] = _fake_user
    app.dependency_overrides[notebooks_module.get_byok_api_key] = lambda: {
        "api_key": None,
        "api_base_url": None,
    }

    with _build_client() as client:
        response = client.post(
            f"/api/v1/notebooks/{notebook_id}/sessions",
            json={"resource_id": str(resource_id), "mode": "learn"},
        )

    assert response.status_code == 201
    assert calls["curriculum"] == 1

    app.dependency_overrides.clear()


def test_http_notebook_doubt_session_skips_curriculum_preparation(monkeypatch):
    user_id = uuid4()
    notebook_id = uuid4()
    resource_id = uuid4()
    session_id = uuid4()
    calls = {"curriculum": 0}

    async def _fake_user():
        return SimpleNamespace(id=user_id)

    async def _fake_owner(*_args, **_kwargs):
        return SimpleNamespace(id=notebook_id)

    class _NotebookResourceRepo:
        def __init__(self, _db):
            pass

        async def get_by_pair(self, _notebook_id, _resource_id):
            return SimpleNamespace(notebook_id=notebook_id, resource_id=resource_id)

    class _ResourceRepo:
        def __init__(self, _db):
            pass

        async def get_by_id(self, _resource_id):
            return SimpleNamespace(
                id=resource_id,
                owner_user_id=user_id,
                filename="chapter-2.pdf",
                capabilities_json={
                    "can_answer_doubts": True,
                    "vector_search_ready": True,
                },
                file_path_or_uri=None,
            )

    class _NotebookSessionRepo:
        def __init__(self, _db):
            pass

        async def get_by_pair(self, _notebook_id, _session_id):
            return None

        async def create(self, notebook_session):
            notebook_session.id = uuid4()
            notebook_session.started_at = "2026-03-08T00:00:00Z"
            notebook_session.ended_at = None
            notebook_session.created_at = "2026-03-08T00:00:00Z"
            notebook_session.updated_at = "2026-03-08T00:00:00Z"
            return notebook_session

    class _UserRepo:
        def __init__(self, _db):
            pass

        async def get_global_consent(self, _user):
            return (False, None)

    class _PreparationService:
        def __init__(self, _db):
            pass

        async def prepare_session_context(self, **_kwargs):
            return {
                "scope_type": "single_resource",
                "scope_resource_ids": [str(resource_id)],
            }

    class _BatchedCurriculumPreparationService:
        def __init__(self, _db, **_kwargs):
            pass

        async def ensure_curriculum_ready(self, _resource_id):
            calls["curriculum"] += 1
            return {"prepared": True}

    class _SessionService:
        def __init__(self, _db, _curriculum_agent):
            pass

        async def create_session(self, **_kwargs):
            return SimpleNamespace(
                id=session_id,
                user_id=user_id,
                resource_id=resource_id,
                status="active",
                consent_training=False,
                mastery=None,
                plan_state={},
                created_at="2026-03-08T00:00:00Z",
            )

    monkeypatch.setattr(
        notebooks_module, "NotebookResourceRepository", _NotebookResourceRepo
    )
    monkeypatch.setattr(notebooks_module, "ResourceRepository", _ResourceRepo)
    monkeypatch.setattr(
        notebooks_module, "NotebookSessionRepository", _NotebookSessionRepo
    )
    monkeypatch.setattr(notebooks_module, "UserProfileRepository", _UserRepo)
    monkeypatch.setattr(
        notebooks_module, "NotebookPreparationService", _PreparationService
    )
    monkeypatch.setattr(
        notebooks_module, "BatchedCurriculumPreparationService", _BatchedCurriculumPreparationService
    )
    monkeypatch.setattr(notebooks_module, "SessionService", _SessionService)
    monkeypatch.setattr(
        notebooks_module, "CurriculumAgent", lambda *_args, **_kwargs: SimpleNamespace()
    )
    monkeypatch.setattr(notebooks_module, "verify_notebook_owner", _fake_owner)
    monkeypatch.setattr(
        notebooks_module,
        "create_embedding_provider",
        lambda *_args, **_kwargs: SimpleNamespace(embed=lambda *_a, **_k: []),
    )
    monkeypatch.setattr(
        notebooks_module,
        "create_llm_provider",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    app.dependency_overrides[notebooks_module.require_auth] = _fake_user
    app.dependency_overrides[notebooks_module.get_byok_api_key] = lambda: {
        "api_key": None,
        "api_base_url": None,
    }

    with _build_client() as client:
        response = client.post(
            f"/api/v1/notebooks/{notebook_id}/sessions",
            json={"resource_id": str(resource_id), "mode": "doubt"},
        )

    assert response.status_code == 201
    assert calls["curriculum"] == 0

    app.dependency_overrides.clear()
