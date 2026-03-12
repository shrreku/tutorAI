from datetime import datetime, timezone
from types import SimpleNamespace
import uuid

import pytest

import app.worker as worker_module


class _FakeSession:
    def __init__(self, resources: dict, jobs: list):
        self.resources = resources
        self.jobs = jobs
        self.commit_calls = 0
        self.rollback_calls = 0

    async def get(self, model, resource_id):
        return self.resources.get(resource_id)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1


class _FakeSessionFactory:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeJobRepo:
    def __init__(self, db):
        self.db = db

    async def get_active_jobs(self):
        return self.db.jobs

    async def get_by_id(self, job_id):
        for job in self.db.jobs:
            if job.id == job_id:
                return job
        return None


@pytest.mark.asyncio
async def test_reconcile_orphaned_jobs_requeues_pending_and_fails_running(monkeypatch):
    pending_resource = SimpleNamespace(
        id=uuid.uuid4(),
        filename="pending.pdf",
        status="processing",
        error_message=None,
    )
    running_resource = SimpleNamespace(
        id=uuid.uuid4(),
        filename="running.pdf",
        status="processing",
        error_message=None,
    )

    pending_job = SimpleNamespace(
        id=uuid.uuid4(),
        resource_id=pending_resource.id,
        status="pending",
        current_stage=None,
        progress_percent=0,
        error_stage=None,
        error_message=None,
        started_at=None,
        completed_at=None,
    )
    running_job = SimpleNamespace(
        id=uuid.uuid4(),
        resource_id=running_resource.id,
        status="running",
        current_stage="enrich",
        progress_percent=45,
        error_stage=None,
        error_message=None,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
    )
    fake_session = _FakeSession(
        resources={
            pending_resource.id: pending_resource,
            running_resource.id: running_resource,
        },
        jobs=[pending_job, running_job],
    )

    enqueued: list[tuple[str, str]] = []

    async def _fake_queued_job_ids():
        return set()

    async def _fake_enqueue(resource_id: str, job_id: str):
        enqueued.append((resource_id, job_id))

    monkeypatch.setattr(worker_module, "IngestionJobRepository", _FakeJobRepo)
    monkeypatch.setattr(worker_module, "async_session_factory", _FakeSessionFactory(fake_session))
    monkeypatch.setattr(worker_module, "queued_job_ids", _fake_queued_job_ids)
    monkeypatch.setattr(worker_module, "enqueue_ingestion_job", _fake_enqueue)

    summary = await worker_module.reconcile_orphaned_jobs()

    assert summary == {"requeued_pending": 1, "failed_running": 1}
    assert enqueued == [(str(pending_resource.id), str(pending_job.id))]
    assert pending_job.status == "pending"
    assert running_job.status == "failed"
    assert running_job.current_stage == "failed"
    assert running_job.error_stage == "enrich"
    assert running_job.completed_at is not None
    assert running_resource.status == "failed"
    assert "worker restart" in (running_resource.error_message or "")
    assert fake_session.commit_calls == 1


@pytest.mark.asyncio
async def test_reconcile_orphaned_jobs_does_not_duplicate_queued_pending_jobs(monkeypatch):
    resource = SimpleNamespace(
        id=uuid.uuid4(),
        filename="queued.pdf",
        status="processing",
        error_message=None,
    )
    job = SimpleNamespace(
        id=uuid.uuid4(),
        resource_id=resource.id,
        status="pending",
        current_stage=None,
        progress_percent=0,
        error_stage=None,
        error_message=None,
        started_at=None,
        completed_at=None,
    )
    fake_session = _FakeSession(resources={resource.id: resource}, jobs=[job])

    enqueued: list[tuple[str, str]] = []

    async def _fake_queued_job_ids():
        return {str(job.id)}

    async def _fake_enqueue(resource_id: str, job_id: str):
        enqueued.append((resource_id, job_id))

    monkeypatch.setattr(worker_module, "IngestionJobRepository", _FakeJobRepo)
    monkeypatch.setattr(worker_module, "async_session_factory", _FakeSessionFactory(fake_session))
    monkeypatch.setattr(worker_module, "queued_job_ids", _fake_queued_job_ids)
    monkeypatch.setattr(worker_module, "enqueue_ingestion_job", _fake_enqueue)

    summary = await worker_module.reconcile_orphaned_jobs()

    assert summary == {"requeued_pending": 0, "failed_running": 0}
    assert enqueued == []
    assert fake_session.commit_calls == 1


class _FakeSequencedSessionFactory:
    def __init__(self, sessions):
        self._sessions = list(sessions)

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._sessions.pop(0)

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_process_job_finalizes_reserved_ingestion_credits(monkeypatch):
    job = SimpleNamespace(
        id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        status="pending",
        current_stage=None,
        progress_percent=0,
        metrics={"billing": {"reserved_credits": 750, "estimated_credits": 750, "status": "reserved"}},
        started_at=None,
        completed_at=None,
    )
    fake_session = _FakeSession(resources={}, jobs=[job])
    finalized = []

    class _Meter:
        def __init__(self, _db):
            pass

        async def finalize_ingestion(self, user_id, job_id, actual_credits, reserved_credits):
            finalized.append((user_id, job_id, actual_credits, reserved_credits))

    class _Pipeline:
        def __init__(self, **_kwargs):
            pass

        async def run(self, *_args, **_kwargs):
            return {}

    async def _fake_continue_background_curriculum_preparation(**_kwargs):
        return {}

    monkeypatch.setattr(worker_module, "CreditMeter", _Meter)
    monkeypatch.setattr(worker_module, "IngestionJobRepository", _FakeJobRepo)
    monkeypatch.setattr(worker_module, "async_session_factory", _FakeSequencedSessionFactory([fake_session]))
    monkeypatch.setattr(worker_module, "create_llm_provider", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(worker_module, "create_embedding_provider", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(worker_module, "create_storage_provider", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(worker_module, "IngestionPipeline", _Pipeline)
    monkeypatch.setattr(worker_module, "_continue_background_curriculum_preparation", _fake_continue_background_curriculum_preparation)

    result = await worker_module.process_job({"resource_id": str(job.resource_id), "job_id": str(job.id)})

    assert result is True
    assert finalized == [(job.owner_user_id, str(job.id), 750, 750)]
    assert job.metrics["billing"]["status"] == "finalized"


@pytest.mark.asyncio
async def test_process_job_releases_reserved_ingestion_credits_on_failure(monkeypatch):
    monkeypatch.setattr(worker_module.settings, "INGESTION_WORKER_MAX_RETRIES", 1, raising=False)

    job = SimpleNamespace(
        id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        status="pending",
        current_stage=None,
        progress_percent=0,
        retry_count=0,
        error_message=None,
        metrics={"billing": {"reserved_credits": 900, "estimated_credits": 900, "status": "reserved"}},
        started_at=None,
        completed_at=None,
    )
    first_session = _FakeSession(resources={}, jobs=[job])
    second_session = _FakeSession(resources={}, jobs=[job])
    released = []
    dlq = []

    class _Meter:
        def __init__(self, _db):
            pass

        async def release_ingestion(self, user_id, job_id, reserved_credits):
            released.append((user_id, job_id, reserved_credits))

    class _Pipeline:
        def __init__(self, **_kwargs):
            pass

        async def run(self, *_args, **_kwargs):
            raise RuntimeError("pipeline failed")

    async def _fake_dlq(payload, error):
        dlq.append((payload, error))

    monkeypatch.setattr(worker_module, "CreditMeter", _Meter)
    monkeypatch.setattr(worker_module, "IngestionJobRepository", _FakeJobRepo)
    monkeypatch.setattr(worker_module, "async_session_factory", _FakeSequencedSessionFactory([first_session, second_session]))
    monkeypatch.setattr(worker_module, "create_llm_provider", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(worker_module, "create_embedding_provider", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(worker_module, "create_storage_provider", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(worker_module, "IngestionPipeline", _Pipeline)
    monkeypatch.setattr(worker_module, "send_to_dlq", _fake_dlq)

    result = await worker_module.process_job({"resource_id": str(job.resource_id), "job_id": str(job.id)})

    assert result is False
    assert released == [(job.owner_user_id, str(job.id), 900)]
    assert job.metrics["billing"]["status"] == "released"
    assert dlq


@pytest.mark.asyncio
async def test_process_job_uses_async_byok_escrow_when_present(monkeypatch):
    job = SimpleNamespace(
        id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        status="pending",
        current_stage=None,
        progress_percent=0,
        metrics={
            "billing": {"reserved_credits": 0, "estimated_credits": 0, "status": "not_applicable"},
            "async_byok": {"enabled": True, "escrow_id": str(uuid.uuid4()), "status": "active"},
        },
        started_at=None,
        completed_at=None,
    )
    fake_session = _FakeSession(resources={}, jobs=[job])
    create_calls = []
    finalized = []

    class _EscrowService:
        def __init__(self, _repo):
            pass

        async def decrypt_for_ingestion(self, *, escrow_id, resource_id, job_id):
            return SimpleNamespace(
                api_key="sk-user-key",
                api_base_url="https://api.openai.com/v1",
                provider_name="openai-compatible",
                escrow_id=str(escrow_id),
            )

        async def finalize_job_escrow(self, escrow_id, *, reason, success):
            finalized.append((str(escrow_id), reason, success))

    class _Pipeline:
        def __init__(self, **_kwargs):
            pass

        async def run(self, *_args, **_kwargs):
            return {}

    async def _fake_continue_background_curriculum_preparation(**_kwargs):
        return {}

    def _fake_create_llm_provider(_settings, **kwargs):
        create_calls.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(worker_module, "AsyncByokEscrowService", _EscrowService)
    monkeypatch.setattr(worker_module, "AsyncByokEscrowRepository", lambda _db: object())
    monkeypatch.setattr(worker_module, "IngestionJobRepository", _FakeJobRepo)
    monkeypatch.setattr(worker_module, "async_session_factory", _FakeSequencedSessionFactory([fake_session]))
    monkeypatch.setattr(worker_module, "create_llm_provider", _fake_create_llm_provider)
    monkeypatch.setattr(worker_module, "create_embedding_provider", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(worker_module, "create_storage_provider", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(worker_module, "IngestionPipeline", _Pipeline)
    monkeypatch.setattr(worker_module, "_continue_background_curriculum_preparation", _fake_continue_background_curriculum_preparation)

    result = await worker_module.process_job(
        {"resource_id": str(job.resource_id), "job_id": str(job.id), "escrow_id": job.metrics["async_byok"]["escrow_id"]}
    )

    assert result is True
    assert create_calls[0]["byok_api_key"] == "sk-user-key"
    assert create_calls[0]["byok_api_base_url"] == "https://api.openai.com/v1"
    assert finalized == [(job.metrics["async_byok"]["escrow_id"], "ingestion_complete", True)]
    assert job.metrics["async_byok"]["status"] == "consumed"