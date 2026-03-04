import asyncio
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.datastructures import UploadFile

from app.api.v1 import auth as auth_module
from app.api.v1 import ingest as ingest_module
from app.config import settings
import app.db.repositories.ingestion_repo as ingestion_repo_module


class _DummyDb:
    async def commit(self):
        return None


def test_register_rejects_existing_email(monkeypatch):
    class _Repo:
        def __init__(self, _db):
            pass

        async def get_by_email(self, _email):
            return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(auth_module, "UserProfileRepository", _Repo)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_module.register(
                body=auth_module.RegisterRequest(
                    email="existing@example.com",
                    password="Password123!",
                    display_name="Existing",
                    consent_training=False,
                ),
                db=_DummyDb(),
                _=None,
            )
        )

    assert exc.value.status_code == 409


def test_login_returns_token_and_user_payload(monkeypatch):
    password = "Password123!"
    hashed = auth_module._hash_password(password)
    user_id = uuid4()

    class _Repo:
        def __init__(self, _db):
            pass

        async def get_by_email(self, _email):
            return SimpleNamespace(
                id=user_id,
                external_id="login@example.com",
                email="login@example.com",
                display_name="Login User",
                password_hash=hashed,
                preferences={"consent_training_global": True},
            )

    monkeypatch.setattr(auth_module, "UserProfileRepository", _Repo)

    response = asyncio.run(
        auth_module.login(
            body=auth_module.LoginRequest(email="login@example.com", password=password),
            db=_DummyDb(),
            _=None,
        )
    )

    assert response.access_token
    assert response.user.id == str(user_id)
    assert response.user.consent_training_global is True


def test_ingest_upload_rejects_unsupported_extension(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_UPLOADS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "AUTH_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "UPLOAD_ALLOWED_EXTENSIONS", ".pdf,.md", raising=False)
    monkeypatch.setattr(settings, "INGESTION_MAX_CONCURRENT_JOBS", 3, raising=False)
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

    upload = UploadFile(filename="notes.exe", file=BytesIO(b"hello"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            ingest_module.upload_resource(
                background_tasks=BackgroundTasks(),
                file=upload,
                topic="architecture",
                db=_DummyDb(),
                user=SimpleNamespace(id=uuid4()),
            )
        )

    assert exc.value.status_code == 400
    assert "Unsupported file type" in str(exc.value.detail)


def test_ingest_upload_rejects_when_queue_full(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_UPLOADS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "AUTH_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "UPLOAD_ALLOWED_EXTENSIONS", ".pdf,.md", raising=False)
    monkeypatch.setattr(settings, "INGESTION_MAX_CONCURRENT_JOBS", 1, raising=False)
    monkeypatch.setattr(settings, "INGESTION_QUEUE_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "REDIS_URL", None, raising=False)

    class _JobRepo:
        def __init__(self, _db):
            pass

        async def expire_stale_active_jobs(self, max_age_minutes=5):
            return 0

        async def count_active_jobs(self, include_pending=True):
            return 1

    monkeypatch.setattr(ingestion_repo_module, "IngestionJobRepository", _JobRepo)

    upload = UploadFile(filename="doc.pdf", file=BytesIO(b"hello"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            ingest_module.upload_resource(
                background_tasks=BackgroundTasks(),
                file=upload,
                topic="architecture",
                db=_DummyDb(),
                user=SimpleNamespace(id=uuid4()),
            )
        )

    assert exc.value.status_code == 429
    assert "queue is full" in str(exc.value.detail)


def test_get_ingestion_status_forbidden_for_non_owner(monkeypatch):
    class _JobRepo:
        def __init__(self, _db):
            pass

        async def get_by_id(self, _job_id):
            return SimpleNamespace(
                id=uuid4(),
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

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            ingest_module.get_ingestion_status(
                job_id=uuid4(),
                db=_DummyDb(),
                user=SimpleNamespace(id=uuid4()),
            )
        )

    assert exc.value.status_code == 403
