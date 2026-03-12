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
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from urllib.parse import urlparse

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
from app.services.curriculum_preparation import CurriculumPreparationService
from app.services.ingestion.enricher import ChunkEnricher
from app.services.ingestion.ontology_extractor import OntologyExtractor
from app.services.ingestion.pipeline import IngestionPipeline
from app.services.ingestion.pipeline_support import update_job
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


def _get_curriculum_billing_state(job) -> dict:
    metrics = getattr(job, "metrics", None) or {}
    if not isinstance(metrics, dict):
        metrics = {}
    curriculum_billing = metrics.get("curriculum_billing")
    if not isinstance(curriculum_billing, dict):
        curriculum_billing = {}
    return curriculum_billing


def _estimate_curriculum_from_job(*, meter: CreditMeter, resource, job) -> dict:
    metrics = getattr(job, "metrics", None) or {}
    billing = metrics.get("billing") if isinstance(metrics, dict) else {}
    document = metrics.get("document") if isinstance(metrics, dict) else {}
    file_size_bytes = int((billing or {}).get("file_size_bytes") or 0)
    if file_size_bytes <= 0 and getattr(resource, "file_path_or_uri", None) and urlparse(resource.file_path_or_uri).scheme in {"", "file"}:
        try:
            file_size_bytes = Path(resource.file_path_or_uri).stat().st_size
        except OSError:
            file_size_bytes = 0
    return meter.estimate_curriculum_preparation_v2(
        file_size_bytes=file_size_bytes,
        filename=resource.filename,
        page_count_estimate=int((document or {}).get("page_count_actual") or 0),
        token_count_estimate=int((document or {}).get("token_count_actual") or 0),
        chunk_count_estimate=int((document or {}).get("chunk_count_actual") or 0),
    )


async def _release_curriculum_reservation(meter: CreditMeter, *, user_id, curriculum_billing: dict) -> None:
    reserved_credits = int(curriculum_billing.get("reserved_credits") or 0)
    operation_id = curriculum_billing.get("operation_id")
    if reserved_credits <= 0 or not operation_id:
        return
    await meter.release_operation(
        user_id,
        UUID(str(operation_id)),
        reserved_credits,
        reference_id=str(operation_id),
        reference_type="curriculum_prepare",
    )


def _handle_signal(*_):
    logger.info("Shutdown signal received – finishing current job…")
    _shutdown.set()


async def _continue_background_curriculum_preparation(
    *,
    db,
    resource_uuid: UUID,
    job,
    byok_api_key: str | None,
    byok_api_base_url: str | None,
) -> dict:
    meter = CreditMeter(db)
    resource = await db.get(Resource, resource_uuid)
    if resource is None:
        raise ValueError(f"Resource {resource_uuid} not found")

    curriculum_estimate = _estimate_curriculum_from_job(meter=meter, resource=resource, job=job)
    op = await meter.create_operation(
        job.owner_user_id,
        "curriculum_prepare",
        resource_id=str(resource_uuid),
        selected_model_id=settings.LLM_MODEL_ONTOLOGY or settings.LLM_MODEL,
        estimate_credits_low=int(curriculum_estimate.get("estimated_credits_low") or 0),
        estimate_credits_high=int(curriculum_estimate.get("estimated_credits_high") or 0),
        metadata={"job_id": str(job.id), "source": "background_ingestion"},
    )
    reserved_credits = await meter.reserve_operation(
        job.owner_user_id,
        op.id,
        int(curriculum_estimate.get("estimated_credits_high") or 0),
        reference_id=str(op.id),
        reference_type="curriculum_prepare",
    )
    if reserved_credits is None:
        job.metrics = {
            **(job.metrics or {}),
            "capability_progress": {
                "search_ready": True,
                "doubt_ready": True,
                "learn_ready": False,
            },
            "curriculum_billing": {
                "estimated_credits_low": int(curriculum_estimate.get("estimated_credits_low") or 0),
                "estimated_credits_high": int(curriculum_estimate.get("estimated_credits_high") or 0),
                "reserved_credits": 0,
                "actual_credits": None,
                "status": "blocked_insufficient_credits",
                "operation_id": str(op.id),
                "release_reason": None,
            },
            "curriculum_preparation": {"prepared": False, "reason": "insufficient_credits"},
        }
        await update_job(db, job.id, "completed", "complete", 100, metrics=job.metrics)
        await db.commit()
        return {"prepared": False, "reason": "insufficient_credits"}

    job.metrics = {
        **(job.metrics or {}),
        "curriculum_billing": {
            "estimated_credits_low": int(curriculum_estimate.get("estimated_credits_low") or 0),
            "estimated_credits_high": int(curriculum_estimate.get("estimated_credits_high") or 0),
            "reserved_credits": reserved_credits,
            "actual_credits": None,
            "status": "reserved",
            "operation_id": str(op.id),
            "release_reason": None,
        },
    }
    await db.commit()

    async def _progress(stage: str, progress: int) -> None:
        current_metrics = dict(job.metrics or {})
        await update_job(
            db,
            job.id,
            "running",
            stage,
            progress,
            metrics=current_metrics,
        )
        await db.commit()

    embedding_provider = create_embedding_provider(settings)
    ontology_llm = create_llm_provider(
        settings,
        task="ontology",
        byok_api_key=byok_api_key,
        byok_api_base_url=byok_api_base_url,
    )
    enrichment_llm = create_llm_provider(
        settings,
        task="enrichment",
        byok_api_key=byok_api_key,
        byok_api_base_url=byok_api_base_url,
    )
    service = CurriculumPreparationService(
        db,
        ontology_extractor=OntologyExtractor(
            ontology_llm,
            ontology_model=settings.LLM_MODEL_ONTOLOGY,
            embed_fn=embedding_provider.embed,
        ),
        enricher=ChunkEnricher(
            enrichment_llm,
            enrichment_model=settings.LLM_MODEL_ENRICHMENT,
        ),
    )
    ontology_before = dict(getattr(ontology_llm, "total_tokens_used", None) or {"prompt_tokens": 0, "completion_tokens": 0})
    enrichment_before = dict(getattr(enrichment_llm, "total_tokens_used", None) or {"prompt_tokens": 0, "completion_tokens": 0})
    summary = await service.ensure_curriculum_ready(resource_uuid, progress_callback=_progress)
    ontology_after = dict(getattr(ontology_llm, "total_tokens_used", None) or {"prompt_tokens": 0, "completion_tokens": 0})
    enrichment_after = dict(getattr(enrichment_llm, "total_tokens_used", None) or {"prompt_tokens": 0, "completion_tokens": 0})
    ontology_prompt = max(0, int(ontology_after.get("prompt_tokens", 0)) - int(ontology_before.get("prompt_tokens", 0)))
    ontology_completion = max(0, int(ontology_after.get("completion_tokens", 0)) - int(ontology_before.get("completion_tokens", 0)))
    enrichment_prompt = max(0, int(enrichment_after.get("prompt_tokens", 0)) - int(enrichment_before.get("prompt_tokens", 0)))
    enrichment_completion = max(0, int(enrichment_after.get("completion_tokens", 0)) - int(enrichment_before.get("completion_tokens", 0)))
    if ontology_prompt or ontology_completion:
        await meter.append_usage_line(
            op.id,
            "curriculum_ontology",
            settings.LLM_MODEL_ONTOLOGY or settings.LLM_MODEL,
            input_tokens=ontology_prompt,
            output_tokens=ontology_completion,
        )
    if enrichment_prompt or enrichment_completion:
        await meter.append_usage_line(
            op.id,
            "curriculum_enrichment",
            settings.LLM_MODEL_ENRICHMENT or settings.LLM_MODEL,
            input_tokens=enrichment_prompt,
            output_tokens=enrichment_completion,
        )
    actual_credits = await meter.finalize_operation(
        job.owner_user_id,
        op.id,
        reserved_credits,
        reference_id=str(op.id),
        reference_type="curriculum_prepare",
    )
    job.metrics = {
        **(job.metrics or {}),
        "capability_progress": {
            "search_ready": True,
            "doubt_ready": True,
            "learn_ready": True,
        },
        "curriculum_billing": {
            "estimated_credits_low": int(curriculum_estimate.get("estimated_credits_low") or 0),
            "estimated_credits_high": int(curriculum_estimate.get("estimated_credits_high") or 0),
            "reserved_credits": reserved_credits,
            "actual_credits": actual_credits,
            "status": "finalized",
            "operation_id": str(op.id),
            "release_reason": None,
        },
        "curriculum_preparation": summary,
    }
    await update_job(
        db,
        job.id,
        "completed",
        "complete",
        100,
        metrics=job.metrics,
    )
    await db.commit()
    return summary


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

            curriculum_billing = _get_curriculum_billing_state(job)
            if owner_user_id and int(curriculum_billing.get("reserved_credits") or 0) > 0 and curriculum_billing.get("status") == "reserved":
                meter = CreditMeter(db)
                await _release_curriculum_reservation(
                    meter,
                    user_id=owner_user_id,
                    curriculum_billing=curriculum_billing,
                )
                job.metrics = {
                    **(job.metrics or {}),
                    "curriculum_billing": {
                        **curriculum_billing,
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
            if job is not None:
                await _continue_background_curriculum_preparation(
                    db=db,
                    resource_uuid=resource_uuid,
                    job=job,
                    byok_api_key=byok_api_key,
                    byok_api_base_url=byok_api_base_url,
                )
                result = {
                    **(result if isinstance(result, dict) else {}),
                    "capability_progress": {
                        "search_ready": True,
                        "doubt_ready": True,
                        "learn_ready": True,
                    },
                }

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

                    # CM-009: Create operation-based metering for measured ingestion
                    if settings.OPERATION_METERING_ENABLED:
                        try:
                            op = await meter.create_operation(
                                job.owner_user_id, "ingestion",
                                resource_id=resource_id,
                                selected_model_id=settings.LLM_MODEL_ONTOLOGY or settings.LLM_MODEL,
                                metadata={"job_id": job_id},
                            )
                            pipeline_metrics = result if isinstance(result, dict) else {}
                            total_tokens = int(pipeline_metrics.get("total_tokens", 0))
                            ontology_tokens = int(pipeline_metrics.get("ontology_tokens", 0))
                            enrichment_tokens = int(pipeline_metrics.get("enrichment_tokens", 0))
                            embed_tokens = int(pipeline_metrics.get("embed_tokens", 0))
                            has_usage_metrics = any(
                                value > 0
                                for value in (total_tokens, ontology_tokens, enrichment_tokens, embed_tokens)
                            )
                            if has_usage_metrics:
                                if ontology_tokens or total_tokens:
                                    await meter.append_usage_line(
                                        op.id, "ontology_extraction",
                                        settings.LLM_MODEL_ONTOLOGY or settings.LLM_MODEL,
                                        input_tokens=int((ontology_tokens or total_tokens * 0.4) * 0.8),
                                        output_tokens=int((ontology_tokens or total_tokens * 0.4) * 0.2),
                                    )
                                if enrichment_tokens or total_tokens:
                                    await meter.append_usage_line(
                                        op.id, "chunk_enrichment",
                                        settings.LLM_MODEL_ENRICHMENT or settings.LLM_MODEL,
                                        input_tokens=int((enrichment_tokens or total_tokens * 0.5) * 0.7),
                                        output_tokens=int((enrichment_tokens or total_tokens * 0.5) * 0.3),
                                    )
                                if embed_tokens or total_tokens:
                                    await meter.append_usage_line(
                                        op.id, "embedding",
                                        settings.EMBEDDING_MODEL_ID or "text-embedding-3-small",
                                        input_tokens=embed_tokens or int(total_tokens * 0.1),
                                        output_tokens=0,
                                    )
                                await meter.finalize_operation(
                                    job.owner_user_id, op.id, 0,
                                    reference_id=job_id,
                                    reference_type="ingestion",
                                )
                            else:
                                await meter.metering_repo.update_operation_status(
                                    op.id,
                                    "finalized",
                                    final_credits=actual_credits,
                                    final_usd=round(meter.credit_units_to_usd(actual_credits), 6),
                                    metadata={
                                        "job_id": job_id,
                                        "finalized_from_job_billing": True,
                                    },
                                )
                                logger.info(
                                    "Finalized ingestion operation %s from job billing metrics: %s credits",
                                    op.id,
                                    actual_credits,
                                )
                        except Exception:
                            logger.warning("CM-009: Failed to create operation-based ingestion metering for job %s", job_id, exc_info=True)
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

            current_curriculum_billing = _get_curriculum_billing_state(job) if job else {}
            if job and job.owner_user_id and int(current_curriculum_billing.get("reserved_credits") or 0) > 0 and current_curriculum_billing.get("status") == "reserved":
                try:
                    async with async_session_factory() as db2:
                        jrepo = IngestionJobRepository(db2)
                        j = await jrepo.get_by_id(UUID(job_id))
                        if j and j.owner_user_id:
                            curriculum_billing = _get_curriculum_billing_state(j)
                            if int(curriculum_billing.get("reserved_credits") or 0) > 0 and curriculum_billing.get("status") == "reserved":
                                meter = CreditMeter(db2)
                                await _release_curriculum_reservation(
                                    meter,
                                    user_id=j.owner_user_id,
                                    curriculum_billing=curriculum_billing,
                                )
                                j.metrics = {
                                    **(j.metrics or {}),
                                    "curriculum_billing": {
                                        **curriculum_billing,
                                        "status": "released",
                                        "release_reason": "worker_failure",
                                    },
                                }
                                await db2.commit()
                except Exception:
                    logger.exception("Could not release curriculum reservation after ingestion failure")

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
                            curriculum_billing = _get_curriculum_billing_state(j)
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
                            if j.owner_user_id and int(curriculum_billing.get("reserved_credits") or 0) > 0 and curriculum_billing.get("status") == "reserved":
                                meter = CreditMeter(db2)
                                await _release_curriculum_reservation(
                                    meter,
                                    user_id=j.owner_user_id,
                                    curriculum_billing=curriculum_billing,
                                )
                                j.metrics = {
                                    **(j.metrics or {}),
                                    "curriculum_billing": {
                                        **curriculum_billing,
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
