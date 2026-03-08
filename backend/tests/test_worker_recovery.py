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

    async def get(self, model, resource_id):
        return self.resources.get(resource_id)

    async def commit(self):
        self.commit_calls += 1


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