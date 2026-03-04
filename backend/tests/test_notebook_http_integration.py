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
        raise HTTPException(status_code=404, detail="Notebook session mapping not found")

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
    app.dependency_overrides[tutor_module.get_byok_api_key] = lambda: {"api_key": None, "api_base_url": None}
    monkeypatch.setattr(tutor_module, "verify_session_owner", _fake_verify_session_owner)
    monkeypatch.setattr(tutor_module, "verify_notebook_session_link", _fake_verify_notebook_session_link)
    monkeypatch.setattr(tutor_module, "SessionRepository", _SessionRepo)
    monkeypatch.setattr(tutor_module, "NotebookResourceRepository", _NotebookResourceRepo)

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
    app.dependency_overrides[tutor_module.get_byok_api_key] = lambda: {"api_key": None, "api_base_url": None}

    with _build_client() as client:
        response = client.post(
            "/api/v1/tutor/turn",
            json={"session_id": str(uuid4()), "message": "hello"},
        )

    assert response.status_code == 410
    assert "removed" in response.json()["detail"]
    app.dependency_overrides.clear()
