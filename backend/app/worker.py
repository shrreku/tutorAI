#!/usr/bin/env python3
"""
Durable ingestion worker — consumes jobs from the Redis queue and runs the
full ingestion pipeline (Docling parse → chunking → embedding → enrichment).

Usage:
    python -m app.worker            # from backend/
    python worker.py                # direct

Behaviour:
  * Block-pops jobs from ``studyagent:ingestion:jobs``.
  * Retries transient failures up to ``INGESTION_WORKER_MAX_RETRIES``.
  * Moves permanently-failed jobs to a dead-letter queue.
  * Updates ``ingestion_job`` rows in Postgres throughout.
  * Gracefully shuts down on SIGINT / SIGTERM.
"""
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.exc import IntegrityError

# Ensure the package root is importable when running ``python worker.py``
if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings
from app.db.database import async_session_factory
from app.db.repositories.async_byok_repo import AsyncByokEscrowRepository
from app.models.resource import Resource
from app.services.ingestion.queue import (
    enqueue_ingestion_job,
    dequeue_ingestion_job,
    queued_job_ids,
    send_to_dlq,
)
from app.services.async_byok_escrow import AsyncByokEscrowService, async_byok_feature_available
from app.services.ingestion.pipeline import IngestionPipeline
from app.services.llm.factory import create_llm_provider, get_missing_platform_llm_config
from app.services.embedding.factory import create_embedding_provider
from app.services.storage.factory import create_storage_provider
from app.services.credits.meter import CreditMeter
from app.db.repositories.ingestion_repo import IngestionJobRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - worker - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ingestion_worker")

_shutdown = asyncio.Event()


def _get_billing_state(job) -> dict:
    metrics = getattr(job, "metrics", None) or {}
    if not isinstance(metrics, dict):
        metrics = {}
    billing = metrics.get("billing")
    if not isinstance(billing, dict):
        billing = {}
    return billing


def _get_async_byok_state(job) -> dict:
    metrics = getattr(job, "metrics", None) or {}
    if not isinstance(metrics, dict):
        metrics = {}
    async_byok = metrics.get("async_byok")
    if not isinstance(async_byok, dict):
        async_byok = {}
    return async_byok


def _handle_signal(*_):
    logger.info("Shutdown signal received – finishing current job…")
    _shutdown.set()


async def reconcile_orphaned_jobs() -> dict[str, int]:
    """Recover queue/database drift after worker restarts.

    Pending jobs can be left in Postgres if the API committed the job row but the
    queue push never completed, or if Redis state was lost during a restart.
    Running jobs cannot be resumed safely because the ingestion pipeline may have
    performed partial writes before the worker died, so they are marked failed and
    must be retried explicitly.
    """
    queued_ids = await queued_job_ids()
    requeued_pending = 0
    failed_running = 0

    async with async_session_factory() as db:
        job_repo = IngestionJobRepository(db)
        active_jobs = await job_repo.get_active_jobs()
        if not active_jobs:
            return {"requeued_pending": 0, "failed_running": 0}

        now = datetime.now(timezone.utc)
        for job in active_jobs:
            job_id = str(job.id)

            if job.status == "pending":
                if job_id in queued_ids:
                    continue
                async_byok = _get_async_byok_state(job)
                escrow_id = async_byok.get("escrow_id")
                if escrow_id:
                    await enqueue_ingestion_job(
                        str(job.resource_id),
                        job_id,
                        escrow_id=escrow_id,
                    )
                else:
                    await enqueue_ingestion_job(str(job.resource_id), job_id)
                queued_ids.add(job_id)
                requeued_pending += 1
                continue

            interruption_stage = job.current_stage or "worker_pickup"
            interruption_message = (
                "Marked failed after worker restart while ingestion was in progress. "
                "Retry the ingestion job to continue processing."
            )
            job.status = "failed"
            job.current_stage = "failed"
            job.error_stage = interruption_stage
            job.error_message = interruption_message
            if job.started_at is None:
                job.started_at = now
            job.completed_at = now

            billing = _get_billing_state(job)
            reserved_credits = int(billing.get("reserved_credits") or 0)
            owner_user_id = getattr(job, "owner_user_id", None)
            if owner_user_id and reserved_credits > 0 and billing.get("status") == "reserved":
                meter = CreditMeter(db)
                await meter.release_ingestion(owner_user_id, job_id, reserved_credits)
                job.metrics = {
                    **(job.metrics or {}),
                    "billing": {
                        **billing,
                        "status": "released",
                        "release_reason": "worker_restart",
                    },
                }

            async_byok = _get_async_byok_state(job)
            if async_byok.get("escrow_id"):
                escrow_service = AsyncByokEscrowService(AsyncByokEscrowRepository(db))
                await escrow_service.finalize_job_escrow(
                    UUID(async_byok["escrow_id"]),
                    reason="worker_restart",
                    success=False,
                )
                job.metrics = {
                    **(job.metrics or {}),
                    "async_byok": {
                        **async_byok,
                        "status": "deleted",
                    },
                }

            resource = await db.get(Resource, job.resource_id)
            if resource is not None:
                resource.status = "failed"
                resource.error_message = interruption_message

            failed_running += 1

        await db.commit()

    if requeued_pending or failed_running:
        logger.info(
            "Recovered ingestion worker state: requeued_pending=%s failed_running=%s",
            requeued_pending,
            failed_running,
        )
    return {
        "requeued_pending": requeued_pending,
        "failed_running": failed_running,
    }


async def process_job(payload: dict, attempt: int = 1) -> bool:
    """Run the ingestion pipeline for one queued job.

    Returns ``True`` on success, ``False`` on permanent failure.
    """
    resource_id = payload["resource_id"]
    job_id = payload["job_id"]
    escrow_id = payload.get("escrow_id")
    max_retries = settings.INGESTION_WORKER_MAX_RETRIES

    async with async_session_factory() as db:
        try:
            resource_uuid = UUID(resource_id)
            job_uuid = UUID(job_id)

            # Mark the job as running
            job_repo = IngestionJobRepository(db)
            job = await job_repo.get_by_id(job_uuid)
            if job:
                job.status = "running"
                job.current_stage = "worker_pickup"
                if job.started_at is None:
                    job.started_at = datetime.now(timezone.utc)
                await db.commit()

            if job:
                job.current_stage = "initializing_models"
                job.progress_percent = max(job.progress_percent or 0, 2)
                await db.commit()

            byok_api_key = None
            byok_api_base_url = None
            resolved_provider_name = None
            if escrow_id:
                escrow_service = AsyncByokEscrowService(AsyncByokEscrowRepository(db))
                resolved = await escrow_service.decrypt_for_ingestion(
                    escrow_id=UUID(str(escrow_id)),
                    resource_id=resource_uuid,
                    job_id=job_uuid,
                )
                byok_api_key = resolved.api_key
                byok_api_base_url = resolved.api_base_url
                resolved_provider_name = resolved.provider_name
                if job:
                    job.metrics = {
                        **(job.metrics or {}),
                        "async_byok": {
                            **_get_async_byok_state(job),
                            "status": "decrypted",
                            "provider_name": resolved_provider_name,
                        },
                    }
                    await db.commit()

            llm_provider = create_llm_provider(
                settings,
                task="ontology",
                byok_api_key=byok_api_key,
                byok_api_base_url=byok_api_base_url,
            )
            embedding_provider = create_embedding_provider(settings)
            storage_provider = create_storage_provider(settings)

            pipeline = IngestionPipeline(
                db_session=db,
                llm_provider=llm_provider,
                embedding_provider=embedding_provider,
                storage_provider=storage_provider,
            )

            result = await pipeline.run(resource_uuid, job_uuid)

            if job and job.owner_user_id:
                billing = _get_billing_state(job)
                reserved_credits = int(billing.get("reserved_credits") or 0)
                if reserved_credits > 0 and billing.get("status") == "reserved":
                    meter = CreditMeter(db)
                    actual_credits = int(billing.get("actual_credits") or billing.get("estimated_credits") or reserved_credits)
                    await meter.finalize_ingestion(
                        job.owner_user_id,
                        job_id,
                        actual_credits,
                        reserved_credits,
                    )
                    job.metrics = {
                        **(job.metrics or {}),
                        "billing": {
                            **billing,
                            "actual_credits": actual_credits,
                            "status": "finalized",
                        },
                    }
                if escrow_id:
                    escrow_service = AsyncByokEscrowService(AsyncByokEscrowRepository(db))
                    await escrow_service.finalize_job_escrow(
                        UUID(str(escrow_id)),
                        reason="ingestion_complete",
                        success=True,
                    )
                    job.metrics = {
                        **(job.metrics or {}),
                        "async_byok": {
                            **_get_async_byok_state(job),
                            "status": "consumed",
                            "provider_name": resolved_provider_name or _get_async_byok_state(job).get("provider_name"),
                        },
                    }
            await db.commit()
            logger.info(f"✓ Completed ingestion for resource {resource_id} (attempt {attempt})")
            return True

        except Exception as exc:
            logger.exception(f"Ingestion failed for resource {resource_id} (attempt {attempt}/{max_retries}): {exc}")
            await db.rollback()
            non_retryable = isinstance(exc, IntegrityError)

            if attempt < max_retries and not non_retryable:
                # Exponential back-off: 2s, 4s, 8s …
                delay = 2 ** attempt
                logger.info(f"Retrying in {delay}s …")
                await asyncio.sleep(delay)
                return await process_job(payload, attempt + 1)
            else:
                # Permanent failure → DLQ
                await send_to_dlq(payload, str(exc))

                # Mark DB row as failed
                try:
                    async with async_session_factory() as db2:
                        jrepo = IngestionJobRepository(db2)
                        j = await jrepo.get_by_id(UUID(job_id))
                        if j:
                            billing = _get_billing_state(j)
                            async_byok = _get_async_byok_state(j)
                            reserved_credits = int(billing.get("reserved_credits") or 0)
                            if j.owner_user_id and reserved_credits > 0 and billing.get("status") == "reserved":
                                meter = CreditMeter(db2)
                                await meter.release_ingestion(j.owner_user_id, job_id, reserved_credits)
                                j.metrics = {
                                    **(j.metrics or {}),
                                    "billing": {
                                        **billing,
                                        "status": "released",
                                        "release_reason": "worker_failure",
                                    },
                                }
                            if async_byok.get("escrow_id"):
                                escrow_service = AsyncByokEscrowService(AsyncByokEscrowRepository(db2))
                                await escrow_service.finalize_job_escrow(
                                    UUID(async_byok["escrow_id"]),
                                    reason="worker_failure",
                                    success=False,
                                )
                                j.metrics = {
                                    **(j.metrics or {}),
                                    "async_byok": {
                                        **async_byok,
                                        "status": "deleted",
                                    },
                                }
                            j.status = "failed"
                            j.current_stage = "failed"
                            j.retry_count = max(j.retry_count, attempt - 1)
                            j.error_message = str(exc)[:2000]
                            if j.started_at is None:
                                j.started_at = datetime.now(timezone.utc)
                            j.completed_at = datetime.now(timezone.utc)
                            await db2.commit()
                except Exception:
                    logger.exception("Could not mark job as failed in DB")

                return False


async def worker_loop():
    """Main loop: continuously dequeue and process ingestion jobs."""
    concurrency = settings.INGESTION_WORKER_CONCURRENCY
    logger.info(
        f"Ingestion worker started (concurrency={concurrency}, "
        f"max_retries={settings.INGESTION_WORKER_MAX_RETRIES})"
    )

    try:
        await reconcile_orphaned_jobs()
    except Exception:
        logger.exception("Failed to reconcile ingestion jobs during worker startup")

    if settings.INGESTION_PREWARM_ENABLED:
        try:
            await asyncio.to_thread(create_embedding_provider, settings)
            logger.info("Embedding provider prewarmed during worker startup")
        except Exception as exc:
            logger.warning("Worker embedding prewarm failed: %s", exc)

    semaphore = asyncio.Semaphore(concurrency)

    async def run_with_semaphore(payload: dict):
        async with semaphore:
            await process_job(payload)

    tasks: set[asyncio.Task] = set()

    while not _shutdown.is_set():
        payload = await dequeue_ingestion_job(timeout=2)
        if payload is None:
            # Clean up finished tasks while idle
            done = {t for t in tasks if t.done()}
            tasks -= done
            continue

        task = asyncio.create_task(run_with_semaphore(payload))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    # Wait for in-flight jobs before exiting
    if tasks:
        logger.info(f"Waiting for {len(tasks)} in-flight jobs to finish…")
        await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("Ingestion worker shut down cleanly.")


def main():
    if not settings.REDIS_URL:
        logger.error("REDIS_URL is required for the ingestion worker. Exiting.")
        sys.exit(1)

    missing_llm = get_missing_platform_llm_config(settings, task="ontology")
    if missing_llm:
        if not async_byok_feature_available():
            logger.error(
                "Worker cannot start because async platform LLM configuration is incomplete: missing %s",
                ", ".join(missing_llm),
            )
            sys.exit(1)
        logger.warning(
            "Worker starting without platform async LLM configuration; only async BYOK escrow jobs can complete until %s is configured",
            ", ".join(missing_llm),
        )

    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    try:
        loop.run_until_complete(worker_loop())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
