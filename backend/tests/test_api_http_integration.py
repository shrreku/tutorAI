from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.db.database import get_db
from app.api.v1 import auth as auth_module
from app.api.v1 import ingest as ingest_module
from app.api.v1 import resources as resources_module
import app.db.repositories.ingestion_repo as ingestion_repo_module


class _DummyDb:
    async def commit(self):
        return None


async def _dummy_db_dep():
    yield _DummyDb()


def _build_client():
    settings.AUTH_ENFORCE_STRONG_SECRET = False
    app.dependency_overrides[get_db] = _dummy_db_dep
    return TestClient(app)


def test_health_endpoint_sets_request_headers():
    with _build_client() as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id")
    assert response.headers.get("X-Response-Time-Ms") is not None
    app.dependency_overrides.clear()


def test_http_auth_register_conflict(monkeypatch):
    class _Repo:
        def __init__(self, _db):
            pass

        async def get_by_email(self, _email):
            return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(auth_module, "UserProfileRepository", _Repo)

    with _build_client() as client:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "exists@example.com",
                "password": "Password123!",
                "display_name": "Exists",
                "consent_training": False,
            },
        )

    assert response.status_code == 409
    app.dependency_overrides.clear()


def test_http_auth_login_success(monkeypatch):
    password = "Password123!"
    hashed = auth_module._hash_password(password)
    user_id = uuid4()

    class _Repo:
        def __init__(self, _db):
            pass

        async def get_by_email(self, _email):
            return SimpleNamespace(
                id=user_id,
                external_id="ok@example.com",
                email="ok@example.com",
                display_name="OK",
                password_hash=hashed,
                preferences={"consent_training_global": True},
            )

    monkeypatch.setattr(auth_module, "UserProfileRepository", _Repo)

    with _build_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ok@example.com", "password": password},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"]
    assert payload["user"]["id"] == str(user_id)
    app.dependency_overrides.clear()


def test_http_ingest_upload_unsupported_extension(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_UPLOADS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "AUTH_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "UPLOAD_ALLOWED_EXTENSIONS", ".pdf,.md", raising=False)
    monkeypatch.setattr(settings, "INGESTION_MAX_CONCURRENT_JOBS", 2, raising=False)
    monkeypatch.setattr(settings, "INGESTION_QUEUE_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "REDIS_URL", None, raising=False)

    class _JobRepo:
        def __init__(self, _db):
            pass

        async def expire_stale_active_jobs(self, max_age_minutes=5):
            return 0

        async def count_active_jobs(self, include_pending=True):
            return 0

    monkeypatch.setattr(ingestion_repo_module, "IngestionJobRepository", _JobRepo)

    async def _fake_user():
        return SimpleNamespace(id=uuid4())

    app.dependency_overrides[ingest_module.require_auth] = _fake_user

    with _build_client() as client:
        response = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("bad.exe", BytesIO(b"test"), "application/octet-stream")},
            data={"topic": "architecture"},
        )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]
    app.dependency_overrides.clear()


def test_http_ingest_status_forbidden_for_non_owner(monkeypatch):
    job_id = uuid4()

    class _JobRepo:
        def __init__(self, _db):
            pass

        async def get_by_id(self, _job_id):
            return SimpleNamespace(
                id=job_id,
                resource_id=uuid4(),
                owner_user_id=uuid4(),
                status="pending",
                current_stage="queue",
                progress_percent=0,
                error_message=None,
                started_at=datetime.utcnow(),
                completed_at=None,
            )

    monkeypatch.setattr(ingest_module, "IngestionJobRepository", _JobRepo)

    async def _fake_user():
        return SimpleNamespace(id=uuid4())

    app.dependency_overrides[ingest_module.require_auth] = _fake_user

    with _build_client() as client:
        response = client.get(f"/api/v1/ingest/status/{job_id}")

    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_http_resources_list_includes_latest_job(monkeypatch):
    resource_id = uuid4()
    job_id = uuid4()
    owner_id = uuid4()

    class _ResourceRepo:
        def __init__(self, _db):
            pass

        async def list_resources(self, **_kwargs):
            return [
                SimpleNamespace(
                    id=resource_id,
                    filename="notes.pdf",
                    topic="Linear Algebra",
                    status="processing",
                    processing_profile="core_only",
                    capabilities_json={"study_ready": False, "can_answer_doubts": True},
                    uploaded_at=datetime.now(timezone.utc),
                    processed_at=None,
                )
            ]

    class _JobRepo:
        def __init__(self, _db):
            pass

        async def get_latest_by_resource_ids(self, resource_ids):
            assert resource_ids == [resource_id]
            return {
                resource_id: SimpleNamespace(
                    id=job_id,
                    resource_id=resource_id,
                    status="running",
                    job_kind="core_ingest",
                    requested_capability="study_ready",
                    scope_type="resource",
                    scope_key=str(resource_id),
                    current_stage="core_ready",
                    progress_percent=70,
                    error_message=None,
                    started_at=datetime.now(timezone.utc),
                    completed_at=None,
                    metrics={
                        "capability_progress": {
                            "search_ready": True,
                            "doubt_ready": True,
                            "learn_ready": False,
                        }
                    },
                )
            }

    monkeypatch.setattr(resources_module, "ResourceRepository", _ResourceRepo)
    monkeypatch.setattr(resources_module, "IngestionJobRepository", _JobRepo)

    async def _fake_user():
        return SimpleNamespace(id=owner_id)

    app.dependency_overrides[resources_module.require_auth] = _fake_user

    with _build_client() as client:
        response = client.get("/api/v1/resources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["latest_job"]["job_id"] == str(job_id)
    assert payload["items"][0]["latest_job"]["current_stage"] == "core_ready"
    assert payload["items"][0]["latest_job"]["capability_progress"]["doubt_ready"] is True
    app.dependency_overrides.clear()


def test_http_resources_list_normalizes_ready_capabilities_from_timestamps(monkeypatch):
    resource_id = uuid4()
    owner_id = uuid4()

    class _ResourceRepo:
        def __init__(self, _db):
            pass

        async def list_resources(self, **_kwargs):
            return [
                SimpleNamespace(
                    id=resource_id,
                    filename="chapter-2.pdf",
                    topic="Mechanics",
                    status="ready",
                    processing_profile="prepared_for_curriculum",
                    capabilities_json={"study_ready": False, "curriculum_ready": False},
                    uploaded_at=datetime.now(timezone.utc),
                    processed_at=datetime.now(timezone.utc),
                    tutoring_ready_at=datetime.now(timezone.utc),
                    study_ready_at=datetime.now(timezone.utc),
                    curriculum_ready_at=datetime.now(timezone.utc),
                )
            ]

    class _JobRepo:
        def __init__(self, _db):
            pass

        async def get_latest_by_resource_ids(self, resource_ids):
            assert resource_ids == [resource_id]
            return {}

    monkeypatch.setattr(resources_module, "ResourceRepository", _ResourceRepo)
    monkeypatch.setattr(resources_module, "IngestionJobRepository", _JobRepo)

    async def _fake_user():
        return SimpleNamespace(id=owner_id)

    app.dependency_overrides[resources_module.require_auth] = _fake_user

    with _build_client() as client:
        response = client.get("/api/v1/resources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["capabilities"]["study_ready"] is True
    assert payload["items"][0]["capabilities"]["curriculum_ready"] is True
    assert payload["items"][0]["capabilities"]["can_start_revision_session"] is True
    app.dependency_overrides.clear()
