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
from app.services.llm import factory as llm_factory_module


class _DummyDb:
    async def commit(self):
        return None


def test_estimate_retry_credits_uses_cached_file_size_for_s3_uri():
    class _Meter:
        def estimate_ingestion_credits(self, **kwargs):
            assert kwargs["file_size_bytes"] == 4096
            assert kwargs["filename"] == "notes.pdf"
            assert kwargs["processing_profile"] == "core_only"
            return 321

    resource = SimpleNamespace(
        filename="notes.pdf",
        file_path_or_uri="s3://studyagent-prod/uploads/notes.pdf",
        processing_profile="core_only",
    )
    latest_job = SimpleNamespace(metrics={"billing": {"file_size_bytes": 4096}})

    estimated = ingest_module._estimate_retry_credits(resource, latest_job, _Meter())

    assert estimated == 321


def test_estimate_retry_credits_uses_local_stat_when_path_is_local(tmp_path):
    file_path = tmp_path / 'notes.pdf'
    file_path.write_bytes(b'a' * 12)

    captured = {}

    class _Meter:
        def estimate_ingestion_credits(self, **kwargs):
            captured.update(kwargs)
            return 111

    resource = SimpleNamespace(
        filename='notes.pdf',
        file_path_or_uri=str(file_path),
        processing_profile='core_only',
    )

    estimated = ingest_module._estimate_retry_credits(resource, None, _Meter())

    assert estimated == 111
    assert captured['file_size_bytes'] == 12


def test_get_balance_bootstraps_credit_account_when_enabled(monkeypatch):
    user_id = uuid4()
    ensured = []

    class _Repo:
        def __init__(self, _db):
            pass

        async def get_account(self, _user_id):
            return SimpleNamespace(
                balance=250,
                lifetime_granted=500,
                lifetime_used=250,
                plan_tier="free_research",
            )

    class _Meter:
        def __init__(self, _db):
            pass

        async def ensure_account(self, _user_id):
            ensured.append(_user_id)

    from app.api.v1 import billing as billing_module

    monkeypatch.setattr(settings, "CREDITS_ENABLED", True, raising=False)
    monkeypatch.setattr(billing_module, "CreditAccountRepository", _Repo)
    monkeypatch.setattr(billing_module, "CreditMeter", _Meter)

    response = asyncio.run(
        billing_module.get_balance(
            db=_DummyDb(),
            user=SimpleNamespace(id=user_id),
        )
    )

    assert ensured == [user_id]
    assert response.credits_enabled is True
    assert response.balance == 250


def test_estimate_ingestion_credits_uses_v2_range_for_small_markdown():
    meter = ingest_module.CreditMeter(_DummyDb())

    estimate = meter.estimate_ingestion_credits(
        file_size_bytes=265,
        filename="notes.md",
    )

    assert estimate == 50


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


def test_register_issues_signup_grant_when_credits_enabled(monkeypatch):
    created_user_id = uuid4()
    signup_grants = []

    class _Repo:
        def __init__(self, _db):
            pass

        async def get_by_email(self, _email):
            return None

        async def create(self, user):
            user.id = created_user_id
            return user

    class _Meter:
        def __init__(self, _db):
            pass

        async def issue_signup_grant_if_missing(self, user_id):
            signup_grants.append(user_id)

    monkeypatch.setattr(settings, "CREDITS_ENABLED", True, raising=False)
    monkeypatch.setattr(auth_module, "UserProfileRepository", _Repo)
    monkeypatch.setattr(auth_module, "CreditMeter", _Meter)

    response = asyncio.run(
        auth_module.register(
            body=auth_module.RegisterRequest(
                email="new@example.com",
                password="Password123!",
                display_name="New User",
                consent_training=False,
            ),
            db=_DummyDb(),
            _=None,
        )
    )

    assert response.user.id == str(created_user_id)
    assert signup_grants == [created_user_id]


def test_login_returns_token_and_user_payload(monkeypatch):
    password = "Password123!"
    hashed = auth_module._hash_password(password)
    user_id = uuid4()
    monkeypatch.setattr(settings, "ADMIN_EXTERNAL_ID", "login@example.com", raising=False)
    monkeypatch.setattr(settings, "ADMIN_EXTERNAL_IDS", "", raising=False)

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
    assert response.user.is_admin is True


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


def test_ingest_upload_rejects_when_insufficient_credits(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_UPLOADS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "AUTH_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "CREDITS_ENABLED", True, raising=False)
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

    class _Meter:
        def __init__(self, _db):
            pass

        def estimate_ingestion_credits(self, **_kwargs):
            return 1200

        def estimate_ingestion_v2(self, **_kwargs):
            return {
                "core_upload_credits": 1200,
                "core_upload_usd": 9.6,
                "curriculum_credits_low": 0,
                "curriculum_credits_high": 0,
                "curriculum_usd_low": 0.0,
                "curriculum_usd_high": 0.0,
                "estimated_credits_low": 1200,
                "estimated_credits_high": 1200,
                "estimated_usd_low": 9.6,
                "estimated_usd_high": 9.6,
                "page_count_estimate": 1,
                "token_count_estimate": 10,
                "chunk_count_estimate": 1,
                "estimate_confidence": "high",
                "warnings": [],
            }

        async def reserve_for_ingestion(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(ingestion_repo_module, "IngestionJobRepository", _JobRepo)
    monkeypatch.setattr(ingest_module, "CreditMeter", _Meter)

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

    assert exc.value.status_code == 402
    assert "Insufficient credits" in str(exc.value.detail)


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


def test_get_ingestion_status_returns_billing_state(monkeypatch):
    owner_id = uuid4()

    class _JobRepo:
        def __init__(self, _db):
            pass

        async def get_by_id(self, _job_id):
            return SimpleNamespace(
                id=uuid4(),
                resource_id=uuid4(),
                owner_user_id=owner_id,
                status="failed",
                job_kind="core_ingest",
                requested_capability="study_ready",
                scope_type="resource",
                scope_key="resource-1",
                current_stage="failed",
                progress_percent=100,
                error_message="worker died",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                metrics={
                    "billing": {
                        "uses_platform_credits": True,
                        "estimated_credits": 900,
                        "reserved_credits": 900,
                        "actual_credits": None,
                        "status": "released",
                        "release_reason": "worker_failure",
                        "file_size_bytes": 2048,
                    }
                },
            )

    monkeypatch.setattr(ingest_module, "IngestionJobRepository", _JobRepo)

    response = asyncio.run(
        ingest_module.get_ingestion_status(
            job_id=uuid4(),
            db=_DummyDb(),
            user=SimpleNamespace(id=owner_id),
        )
    )

    assert response.billing is not None
    assert response.billing.status == "released"
    assert response.billing.release_reason == "worker_failure"


def test_admin_monthly_grant_skips_users_already_granted_for_period(monkeypatch):
    first_user_id = uuid4()
    second_user_id = uuid4()
    issued = []

    class _ScalarResult:
        def __init__(self, values):
            self._values = values

        def all(self):
            return list(self._values)

    class _Result:
        def __init__(self, values):
            self._values = values

        def scalars(self):
            return _ScalarResult(self._values)

    class _Db:
        def __init__(self):
            self.commit_calls = 0

        async def execute(self, _query):
            return _Result([first_user_id, second_user_id])

        async def commit(self):
            self.commit_calls += 1

    class _Repo:
        def __init__(self, _db):
            pass

        async def has_grant(self, user_id, *, source=None, memo=None):
            assert source == "monthly_grant"
            assert memo == "Monthly research grant (2026-03)"
            return user_id == second_user_id

        async def issue_grant(self, user_id, amount, source, memo, metadata):
            issued.append((user_id, amount, source, memo, metadata["grant_period"]))

    from app.api.v1 import billing as billing_module

    monkeypatch.setattr(billing_module, "CreditAccountRepository", _Repo)

    response = asyncio.run(
        billing_module.admin_issue_monthly_grant(
            request=billing_module.AdminMonthlyGrantRequest(period_key="2026-03"),
            db=_Db(),
            user=SimpleNamespace(id=uuid4(), external_id="admin@example.com"),
        )
    )

    assert response.period_key == "2026-03"
    assert response.granted_user_count == 1
    assert response.skipped_user_count == 1
    assert response.granted_user_ids == [str(first_user_id)]
    assert issued == [(first_user_id, settings.CREDITS_DEFAULT_MONTHLY_GRANT, "monthly_grant", "Monthly research grant (2026-03)", "2026-03")]


def test_async_llm_config_reports_missing_platform_fields(monkeypatch):
    monkeypatch.setattr(settings, "LLM_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "LLM_API_BASE_URL", "", raising=False)
    monkeypatch.setattr(settings, "LLM_MODEL", "", raising=False)
    monkeypatch.setattr(settings, "LLM_MODEL_ONTOLOGY", "", raising=False)

    missing = llm_factory_module.get_missing_platform_llm_config(settings, task="ontology")

    assert missing == ["LLM_API_KEY", "LLM_API_BASE_URL", "LLM_MODEL[ontology]"]


def test_ingest_upload_rejects_when_queue_mode_missing_platform_llm(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_UPLOADS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "AUTH_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "UPLOAD_ALLOWED_EXTENSIONS", ".pdf,.md", raising=False)
    monkeypatch.setattr(settings, "INGESTION_MAX_CONCURRENT_JOBS", 3, raising=False)
    monkeypatch.setattr(settings, "INGESTION_QUEUE_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://redis:6379/0", raising=False)
    monkeypatch.setattr(settings, "LLM_API_KEY", "", raising=False)

    class _JobRepo:
        def __init__(self, _db):
            pass

        async def expire_stale_active_jobs(self, max_age_minutes=5):
            return 0

        async def count_active_jobs(self, include_pending=True):
            return 0

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

    assert exc.value.status_code == 503
    assert "platform-managed async LLM configuration" in str(exc.value.detail)


def test_ingest_upload_uses_async_byok_escrow_and_bypasses_credits(monkeypatch):
    user_id = uuid4()
    enqueue_calls = []
    reserve_calls = []

    monkeypatch.setattr(settings, "FEATURE_UPLOADS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "AUTH_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "BYOK_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ASYNC_BYOK_ESCROW_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "UPLOAD_ALLOWED_EXTENSIONS", ".pdf,.md", raising=False)
    monkeypatch.setattr(settings, "INGESTION_MAX_CONCURRENT_JOBS", 3, raising=False)
    monkeypatch.setattr(settings, "INGESTION_QUEUE_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://redis:6379/0", raising=False)
    monkeypatch.setattr(settings, "LLM_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "LLM_API_BASE_URL", "", raising=False)
    monkeypatch.setattr(settings, "LLM_MODEL", "", raising=False)
    monkeypatch.setattr(settings, "LLM_MODEL_ONTOLOGY", "", raising=False)
    monkeypatch.setattr(settings, "CREDITS_ENABLED", True, raising=False)
    monkeypatch.setattr(ingest_module, "async_byok_feature_available", lambda: True)

    class _JobRepo:
        def __init__(self, _db):
            pass

        async def expire_stale_active_jobs(self, max_age_minutes=5):
            return 0

        async def count_active_jobs(self, include_pending=True):
            return 0

        async def create(self, job):
            return job

    class _ResourceRepo:
        def __init__(self, _db):
            pass

        async def create(self, resource):
            return resource

    class _Meter:
        def __init__(self, _db):
            pass

        def estimate_ingestion_credits(self, **_kwargs):
            return 1200

        def estimate_ingestion_v2(self, **_kwargs):
            return {
                "core_upload_credits": 1200,
                "core_upload_usd": 9.6,
                "curriculum_credits_low": 0,
                "curriculum_credits_high": 0,
                "curriculum_usd_low": 0.0,
                "curriculum_usd_high": 0.0,
                "estimated_credits_low": 1200,
                "estimated_credits_high": 1200,
                "estimated_usd_low": 9.6,
                "estimated_usd_high": 9.6,
                "page_count_estimate": 1,
                "token_count_estimate": 10,
                "chunk_count_estimate": 1,
                "estimate_confidence": "high",
                "warnings": [],
            }

        async def reserve_for_ingestion(self, *_args, **_kwargs):
            reserve_calls.append(True)
            return 1200

        async def release_ingestion(self, *_args, **_kwargs):
            return None

    class _Storage:
        async def save_file(self, _file_content, filename):
            return f"/tmp/{filename}"

    class _EscrowService:
        def __init__(self, _repo):
            pass

        async def create_ingestion_escrow(self, **_kwargs):
            return SimpleNamespace(
                id=uuid4(),
                provider_name="openai-compatible",
                expires_at=datetime.utcnow(),
            )

    async def _fake_enqueue(resource_id_arg: str, job_id_arg: str, *, escrow_id: str | None = None):
        enqueue_calls.append((resource_id_arg, job_id_arg, escrow_id))

    monkeypatch.setattr(ingestion_repo_module, "IngestionJobRepository", _JobRepo)
    monkeypatch.setattr(ingest_module, "IngestionJobRepository", _JobRepo)
    monkeypatch.setattr(ingest_module, "ResourceRepository", _ResourceRepo)
    monkeypatch.setattr(ingest_module, "CreditMeter", _Meter)
    monkeypatch.setattr(ingest_module, "create_storage_provider", lambda _settings: _Storage())
    monkeypatch.setattr(ingest_module, "AsyncByokEscrowService", _EscrowService)
    monkeypatch.setattr(ingest_module, "AsyncByokEscrowRepository", lambda _db: object())
    monkeypatch.setattr("app.services.ingestion.queue.enqueue_ingestion_job", _fake_enqueue)

    response = asyncio.run(
        ingest_module.upload_resource(
            background_tasks=BackgroundTasks(),
            file=UploadFile(filename="doc.pdf", file=BytesIO(b"hello")),
            topic="architecture",
            use_async_byok=True,
            db=_DummyDb(),
            user=SimpleNamespace(id=user_id),
            byok={"api_key": "sk-user-key", "api_base_url": "https://api.openai.com/v1"},
        )
    )

    assert reserve_calls == []
    assert response.billing is not None
    assert response.billing.uses_platform_credits is False
    assert response.async_byok is not None
    assert response.async_byok.enabled is True
    assert enqueue_calls
