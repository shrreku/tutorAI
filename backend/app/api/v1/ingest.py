import logging
from pathlib import Path
from uuid import UUID
from datetime import datetime, timezone
import uuid
from urllib.parse import urlparse

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_byok_api_key, require_auth
from app.config import settings
from app.db.database import get_db
from app.db.repositories.async_byok_repo import AsyncByokEscrowRepository
from app.db.repositories.resource_repo import ResourceRepository
from app.db.repositories.ingestion_repo import IngestionJobRepository
from app.models.resource import Resource
from app.models.ingestion import IngestionJob
from app.models.resource import default_resource_capabilities
from app.models.session import UserProfile
from app.schemas.api import (
    IngestionAsyncByokStatusResponse,
    IngestionBillingStatusResponse,
    IngestionCurriculumBillingStatusResponse,
    IngestionStatusResponse,
)
from app.services.async_byok_escrow import (
    AsyncByokEscrowService,
    async_byok_feature_available,
)
from app.services.credits.meter import CreditMeter
from app.services.batched_curriculum_preparation import BatchedCurriculumPreparationService
from app.services.embedding.factory import create_embedding_provider
from app.services.ingestion.enricher import ChunkEnricher
from app.services.ingestion.ontology_extractor import OntologyExtractor
from app.services.ingestion.pipeline_support import update_job
from app.services.llm.factory import (
    create_llm_provider,
    get_missing_platform_llm_config,
)
from app.services.storage.factory import create_storage_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingestion"])


def _normalize_optional_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _ensure_async_llm_ready_for_queue() -> None:
    """Reject queued ingestion early when platform LLM config is incomplete."""
    missing = get_missing_platform_llm_config(settings, task="ontology")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Uploads require platform-managed async LLM configuration in queue mode. "
                f"Missing: {', '.join(missing)}"
            ),
        )


def _build_billing_metrics(
    *,
    uses_platform_credits: bool,
    estimated_credits: int,
    reserved_credits: int,
    file_size_bytes: int,
) -> dict:
    return {
        "billing": {
            "reference_type": "ingestion",
            "uses_platform_credits": uses_platform_credits,
            "estimated_credits": estimated_credits,
            "reserved_credits": reserved_credits,
            "actual_credits": None,
            "status": "reserved" if reserved_credits > 0 else "not_applicable",
            "file_size_bytes": file_size_bytes,
        }
    }


def _build_async_byok_metrics(
    *, escrow_id: UUID | None, provider_name: str | None, expires_at: datetime | None
) -> dict:
    return {
        "async_byok": {
            "enabled": bool(escrow_id),
            "escrow_id": str(escrow_id) if escrow_id else None,
            "provider_name": provider_name,
            "status": "active" if escrow_id else "disabled",
            "expires_at": expires_at.isoformat() if expires_at else None,
            "revoked_at": None,
        }
    }


def _build_curriculum_billing_metrics(*, estimate: dict) -> dict:
    return {
        "curriculum_billing": {
            "estimated_credits_low": int(estimate.get("curriculum_credits_low") or 0),
            "estimated_credits_high": int(estimate.get("curriculum_credits_high") or 0),
            "reserved_credits": 0,
            "actual_credits": None,
            "status": "pending_background_preparation",
            "operation_id": None,
            "release_reason": None,
        }
    }


def _estimate_retry_credits(
    resource: Resource, latest_job: IngestionJob | None, meter: CreditMeter
) -> int:
    latest_metrics = (latest_job.metrics or {}) if latest_job else {}
    latest_billing = (
        latest_metrics.get("billing") if isinstance(latest_metrics, dict) else None
    )
    if isinstance(latest_billing, dict) and latest_billing.get("estimated_credits"):
        return int(latest_billing["estimated_credits"])

    file_size_bytes = 0
    if isinstance(latest_billing, dict) and latest_billing.get("file_size_bytes"):
        file_size_bytes = int(latest_billing["file_size_bytes"])
    elif resource.file_path_or_uri and urlparse(resource.file_path_or_uri).scheme in {
        "",
        "file",
    }:
        try:
            file_size_bytes = Path(resource.file_path_or_uri).stat().st_size
        except OSError:
            file_size_bytes = 0

    return meter.estimate_ingestion_credits(
        file_size_bytes=file_size_bytes,
        filename=resource.filename,
        processing_profile=resource.processing_profile or "core_only",
    )


def _job_billing_payload(
    job: IngestionJob | None,
) -> IngestionBillingStatusResponse | None:
    metrics = (getattr(job, "metrics", None) or {}) if job else {}
    if not isinstance(metrics, dict):
        return None
    billing = metrics.get("billing")
    if not isinstance(billing, dict):
        return None
    return IngestionBillingStatusResponse(
        uses_platform_credits=bool(billing.get("uses_platform_credits", False)),
        estimated_credits=int(billing.get("estimated_credits") or 0),
        reserved_credits=int(billing.get("reserved_credits") or 0),
        actual_credits=int(billing.get("actual_credits"))
        if billing.get("actual_credits") is not None
        else None,
        status=str(billing.get("status") or "not_applicable"),
        release_reason=billing.get("release_reason"),
        file_size_bytes=int(billing.get("file_size_bytes") or 0),
    )


def _job_async_byok_payload(
    job: IngestionJob | None,
) -> IngestionAsyncByokStatusResponse | None:
    metrics = (getattr(job, "metrics", None) or {}) if job else {}
    if not isinstance(metrics, dict):
        return None
    async_byok = metrics.get("async_byok")
    if not isinstance(async_byok, dict):
        return None
    return IngestionAsyncByokStatusResponse(
        enabled=bool(async_byok.get("enabled", False)),
        escrow_id=UUID(async_byok["escrow_id"])
        if async_byok.get("escrow_id")
        else None,
        provider_name=async_byok.get("provider_name"),
        status=str(async_byok.get("status") or "disabled"),
        expires_at=datetime.fromisoformat(async_byok["expires_at"])
        if async_byok.get("expires_at")
        else None,
        revoked_at=datetime.fromisoformat(async_byok["revoked_at"])
        if async_byok.get("revoked_at")
        else None,
    )


def _job_curriculum_billing_payload(
    job: IngestionJob | None,
) -> IngestionCurriculumBillingStatusResponse | None:
    metrics = (getattr(job, "metrics", None) or {}) if job else {}
    if not isinstance(metrics, dict):
        return None
    curriculum_billing = metrics.get("curriculum_billing")
    if not isinstance(curriculum_billing, dict):
        return None
    return IngestionCurriculumBillingStatusResponse(
        estimated_credits_low=int(curriculum_billing.get("estimated_credits_low") or 0),
        estimated_credits_high=int(
            curriculum_billing.get("estimated_credits_high") or 0
        ),
        reserved_credits=int(curriculum_billing.get("reserved_credits") or 0),
        actual_credits=int(curriculum_billing.get("actual_credits"))
        if curriculum_billing.get("actual_credits") is not None
        else None,
        status=str(curriculum_billing.get("status") or "pending"),
        operation_id=UUID(curriculum_billing["operation_id"])
        if curriculum_billing.get("operation_id")
        else None,
        release_reason=curriculum_billing.get("release_reason"),
    )


def _get_billing_state(job: IngestionJob | None) -> dict:
    metrics = (getattr(job, "metrics", None) or {}) if job else {}
    if not isinstance(metrics, dict):
        return {}
    billing = metrics.get("billing")
    return billing if isinstance(billing, dict) else {}


def _get_async_byok_state(job: IngestionJob | None) -> dict:
    metrics = (getattr(job, "metrics", None) or {}) if job else {}
    if not isinstance(metrics, dict):
        return {}
    async_byok = metrics.get("async_byok")
    return async_byok if isinstance(async_byok, dict) else {}


def _get_curriculum_billing_state(job: IngestionJob | None) -> dict:
    metrics = (getattr(job, "metrics", None) or {}) if job else {}
    if not isinstance(metrics, dict):
        return {}
    curriculum_billing = metrics.get("curriculum_billing")
    return curriculum_billing if isinstance(curriculum_billing, dict) else {}


def _estimate_curriculum_from_job(
    *, meter: CreditMeter, resource: Resource, job: IngestionJob | None
) -> dict:
    metrics = (getattr(job, "metrics", None) or {}) if job else {}
    billing = metrics.get("billing") if isinstance(metrics, dict) else {}
    document = metrics.get("document") if isinstance(metrics, dict) else {}
    file_size_bytes = int((billing or {}).get("file_size_bytes") or 0)
    if (
        file_size_bytes <= 0
        and resource.file_path_or_uri
        and urlparse(resource.file_path_or_uri).scheme in {"", "file"}
    ):
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


async def _release_curriculum_reservation(
    meter: CreditMeter, *, user_id: UUID, curriculum_billing: dict
) -> None:
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


def _job_status_payload(job: IngestionJob) -> IngestionStatusResponse:
    metrics = (getattr(job, "metrics", None) or {}) if job else {}
    document = metrics.get("document") if isinstance(metrics, dict) else None
    capability_progress = (
        metrics.get("capability_progress") if isinstance(metrics, dict) else None
    )
    recovery = metrics.get("recovery") if isinstance(metrics, dict) else None
    resumable = bool(recovery.get("resumable")) if isinstance(recovery, dict) else False
    resume_from_stage = (
        recovery.get("resume_from_stage") if isinstance(recovery, dict) else None
    )
    resume_hint = None
    if resumable:
        if resume_from_stage:
            resume_hint = (
                f"Retry will continue from the last saved {resume_from_stage} checkpoint."
            )
        else:
            resume_hint = "Retry will continue from the last saved checkpoint."
    return IngestionStatusResponse(
        job_id=job.id,
        resource_id=job.resource_id,
        status=job.status,
        job_kind=getattr(job, "job_kind", "core_ingest"),
        requested_capability=getattr(job, "requested_capability", None),
        scope_type=getattr(job, "scope_type", None),
        scope_key=getattr(job, "scope_key", None),
        current_stage=getattr(job, "current_stage", None),
        progress_percent=getattr(job, "progress_percent", 0),
        error_message=getattr(job, "error_message", None),
        error_stage=getattr(job, "error_stage", None),
        resumable=resumable,
        resume_hint=resume_hint,
        last_completed_stage=resume_from_stage,
        started_at=getattr(job, "started_at", None),
        completed_at=getattr(job, "completed_at", None),
        document_metrics=document if isinstance(document, dict) else None,
        capability_progress=capability_progress
        if isinstance(capability_progress, dict)
        else None,
        billing=_job_billing_payload(job),
        curriculum_billing=_job_curriculum_billing_payload(job),
        async_byok=_job_async_byok_payload(job),
    )


async def _continue_background_curriculum_preparation(
    *,
    db: AsyncSession,
    resource_id: UUID,
    job: IngestionJob,
    byok_api_key: str | None,
    byok_api_base_url: str | None,
) -> dict:
    meter = CreditMeter(db)
    resource = await db.get(Resource, resource_id)
    if resource is None:
        raise ValueError(f"Resource {resource_id} not found")

    curriculum_estimate = _estimate_curriculum_from_job(
        meter=meter, resource=resource, job=job
    )
    op = await meter.create_operation(
        job.owner_user_id,
        "curriculum_prepare",
        resource_id=str(resource_id),
        selected_model_id=settings.LLM_MODEL_ONTOLOGY or settings.LLM_MODEL,
        estimate_credits_low=int(curriculum_estimate.get("estimated_credits_low") or 0),
        estimate_credits_high=int(
            curriculum_estimate.get("estimated_credits_high") or 0
        ),
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
                "estimated_credits_low": int(
                    curriculum_estimate.get("estimated_credits_low") or 0
                ),
                "estimated_credits_high": int(
                    curriculum_estimate.get("estimated_credits_high") or 0
                ),
                "reserved_credits": 0,
                "actual_credits": None,
                "status": "blocked_insufficient_credits",
                "operation_id": str(op.id),
                "release_reason": None,
            },
            "curriculum_preparation": {
                "prepared": False,
                "reason": "insufficient_credits",
            },
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
        return {"prepared": False, "reason": "insufficient_credits"}

    job.metrics = {
        **(job.metrics or {}),
        "curriculum_billing": {
            "estimated_credits_low": int(
                curriculum_estimate.get("estimated_credits_low") or 0
            ),
            "estimated_credits_high": int(
                curriculum_estimate.get("estimated_credits_high") or 0
            ),
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
    service = BatchedCurriculumPreparationService(
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
    ontology_before = dict(
        getattr(ontology_llm, "total_tokens_used", None)
        or {"prompt_tokens": 0, "completion_tokens": 0}
    )
    enrichment_before = dict(
        getattr(enrichment_llm, "total_tokens_used", None)
        or {"prompt_tokens": 0, "completion_tokens": 0}
    )
    summary = await service.ensure_curriculum_ready(
        resource_id, progress_callback=_progress
    )
    ontology_after = dict(
        getattr(ontology_llm, "total_tokens_used", None)
        or {"prompt_tokens": 0, "completion_tokens": 0}
    )
    enrichment_after = dict(
        getattr(enrichment_llm, "total_tokens_used", None)
        or {"prompt_tokens": 0, "completion_tokens": 0}
    )

    ontology_prompt = max(
        0,
        int(ontology_after.get("prompt_tokens", 0))
        - int(ontology_before.get("prompt_tokens", 0)),
    )
    ontology_completion = max(
        0,
        int(ontology_after.get("completion_tokens", 0))
        - int(ontology_before.get("completion_tokens", 0)),
    )
    enrichment_prompt = max(
        0,
        int(enrichment_after.get("prompt_tokens", 0))
        - int(enrichment_before.get("prompt_tokens", 0)),
    )
    enrichment_completion = max(
        0,
        int(enrichment_after.get("completion_tokens", 0))
        - int(enrichment_before.get("completion_tokens", 0)),
    )

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
            "ready_batch_count": summary.get("batches_completed", 0),
            "total_batch_count": summary.get("total_batches", 0),
            "progressive_study_ready": summary.get("batches_completed", 0) > 0,
        },
        "curriculum_billing": {
            "estimated_credits_low": int(
                curriculum_estimate.get("estimated_credits_low") or 0
            ),
            "estimated_credits_high": int(
                curriculum_estimate.get("estimated_credits_high") or 0
            ),
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


def _resolve_async_byok_request(*, requested: bool, byok: dict) -> bool:
    if not requested:
        return False
    if not async_byok_feature_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Async BYOK escrow is not enabled on this deployment.",
        )
    if not settings.BYOK_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BYOK is disabled on this deployment.",
        )
    if not byok.get("api_key"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Async BYOK requires a valid BYOK API key in the request headers.",
        )
    return True


async def _mark_dispatch_failure(
    *,
    db: AsyncSession,
    resource_id: UUID | None,
    job_id: UUID,
    owner_user_id: UUID,
    reserved_credits: int,
    escrow_id: UUID | None,
    reason: str,
) -> None:
    meter = CreditMeter(db)
    if reserved_credits > 0:
        await meter.release_ingestion(owner_user_id, str(job_id), reserved_credits)

    job_repo = IngestionJobRepository(db)
    job = await job_repo.get_by_id(job_id)
    if job is not None:
        job.status = "failed"
        job.current_stage = "dispatch_failed"
        job.error_message = reason
        job.completed_at = datetime.now(timezone.utc)
        metrics = dict(job.metrics or {})
        billing = dict(metrics.get("billing") or {})
        if billing:
            billing["status"] = (
                "released"
                if reserved_credits > 0
                else billing.get("status", "not_applicable")
            )
            billing["release_reason"] = "dispatch_failure"
            metrics["billing"] = billing
        async_byok = dict(metrics.get("async_byok") or {})
        if async_byok:
            async_byok["status"] = "deleted"
            metrics["async_byok"] = async_byok
        job.metrics = metrics

    if resource_id is not None:
        resource = await db.get(Resource, resource_id)
        if resource is not None:
            resource.status = "failed"
            resource.error_message = reason

    if escrow_id is not None:
        escrow_service = AsyncByokEscrowService(AsyncByokEscrowRepository(db))
        await escrow_service.finalize_job_escrow(
            escrow_id, reason="dispatch_failure", success=False
        )

    await db.commit()


# ---- CM-008: Ingestion estimate v2 preflight ----


class IngestionEstimateRequest(BaseModel):
    filename: str
    file_size_bytes: int = Field(ge=1)
    page_count_estimate: int = Field(default=0, ge=0)
    token_count_estimate: int = Field(default=0, ge=0)
    chunk_count_estimate: int = Field(default=0, ge=0)
    ontology_model_id: Optional[str] = None
    enrichment_model_id: Optional[str] = None


class IngestionEstimateResponse(BaseModel):
    estimated_credits_low: int
    estimated_credits_high: int
    estimated_usd_low: float
    estimated_usd_high: float
    core_upload_credits: int
    core_upload_usd: float
    curriculum_credits_low: int
    curriculum_credits_high: int
    curriculum_usd_low: float
    curriculum_usd_high: float
    page_count_estimate: int
    token_count_estimate: int
    chunk_count_estimate: int
    estimate_confidence: str
    warnings: list[str]


@router.post("/estimate", response_model=IngestionEstimateResponse)
async def estimate_ingestion(
    request: IngestionEstimateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """CM-008: Pre-upload credit estimate with ranges."""
    meter = CreditMeter(db)
    result = meter.estimate_ingestion_v2(
        file_size_bytes=request.file_size_bytes,
        filename=request.filename,
        page_count_estimate=request.page_count_estimate,
        token_count_estimate=request.token_count_estimate,
        chunk_count_estimate=request.chunk_count_estimate,
    )
    return IngestionEstimateResponse(**result)


@router.post("/upload", response_model=IngestionStatusResponse)
async def upload_resource(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    topic: str = Form(default=None),
    use_async_byok: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
    byok: dict = Depends(get_byok_api_key),
):
    """
    Upload a PDF resource and start ingestion.

    Returns the ingestion job status immediately; processing continues in background.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # --- Upload kill switch ---
    if not settings.FEATURE_UPLOADS_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Uploads are temporarily disabled",
        )

    # --- Per-user daily upload quota ---
    if settings.AUTH_ENABLED:
        from app.db.repositories.resource_repo import ResourceRepository as _RR
        from datetime import timedelta

        _rr = _RR(db)
        today_count = await _rr.count_uploads_since(user.id, timedelta(days=1))
        if today_count >= settings.UPLOAD_MAX_FILES_PER_USER_PER_DAY:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily upload limit reached ({settings.UPLOAD_MAX_FILES_PER_USER_PER_DAY} files). Try again tomorrow.",
                headers={"Retry-After": "86400"},
            )

    # --- Concurrent job guard ---
    from app.db.repositories.ingestion_repo import IngestionJobRepository as _IJR

    _ijr = _IJR(db)
    queue_mode = bool(settings.INGESTION_QUEUE_ENABLED and settings.REDIS_URL)
    byok = byok if isinstance(byok, dict) else {"api_key": None, "api_base_url": None}
    use_async_byok = _normalize_optional_bool(use_async_byok)
    use_async_byok = _resolve_async_byok_request(requested=use_async_byok, byok=byok)
    if queue_mode and not use_async_byok:
        _ensure_async_llm_ready_for_queue()
    await _ijr.expire_stale_active_jobs(max_age_minutes=30 if queue_mode else 5)
    active_jobs = await _ijr.count_active_jobs(include_pending=queue_mode)
    if active_jobs >= settings.INGESTION_MAX_CONCURRENT_JOBS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ingestion queue is full. Please try again shortly.",
            headers={"Retry-After": "120"},
        )

    # --- Extension check ---
    allowed_exts = [e.strip() for e in settings.UPLOAD_ALLOWED_EXTENSIONS.split(",")]
    if not any(file.filename.lower().endswith(ext) for ext in allowed_exts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_exts)}",
        )

    # --- Read and validate file size ---
    file_content = await file.read()
    max_bytes = settings.UPLOAD_MAX_FILE_SIZE_MB * 1024 * 1024
    if len(file_content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {settings.UPLOAD_MAX_FILE_SIZE_MB} MB",
        )
    if not file_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )

    meter = CreditMeter(db)
    job_id = uuid.uuid4()
    resource_id = uuid.uuid4()
    escrow = None
    estimate = meter.estimate_ingestion_v2(
        file_size_bytes=len(file_content),
        filename=file.filename,
    )
    estimated_credits = 0
    reserved_credits = 0
    uses_platform_credits = settings.CREDITS_ENABLED and not use_async_byok
    if uses_platform_credits:
        estimated_credits = int(estimate["core_upload_credits"])
        reserved = await meter.reserve_for_ingestion(
            user.id, str(job_id), estimated_credits
        )
        if reserved is None:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient credits for upload processing. Check your balance in Billing.",
            )
        reserved_credits = reserved

    committed = False
    try:
        storage = create_storage_provider(settings)
        file_path = await storage.save_file(file_content, file.filename)

        resource_repo = ResourceRepository(db)
        resource = Resource(
            id=resource_id,
            filename=file.filename,
            owner_user_id=user.id,
            topic=topic,
            status="processing",
            processing_profile="core_only",
            capabilities_json=default_resource_capabilities(),
            file_path_or_uri=file_path,
            uploaded_at=datetime.now(timezone.utc),
        )
        resource = await resource_repo.create(resource)

        if use_async_byok:
            escrow_service = AsyncByokEscrowService(AsyncByokEscrowRepository(db))
            escrow = await escrow_service.create_ingestion_escrow(
                user_id=user.id,
                resource_id=resource.id,
                job_id=job_id,
                byok_api_key=byok["api_key"],
                byok_api_base_url=byok.get("api_base_url"),
            )

        job_repo = IngestionJobRepository(db)
        job = IngestionJob(
            id=job_id,
            resource_id=resource.id,
            owner_user_id=user.id,
            status="pending",
            job_kind="core_ingest",
            requested_capability="study_ready",
            scope_type="resource",
            scope_key=str(resource.id),
            progress_percent=0,
            metrics={
                **_build_billing_metrics(
                    uses_platform_credits=uses_platform_credits,
                    estimated_credits=estimated_credits,
                    reserved_credits=reserved_credits,
                    file_size_bytes=len(file_content),
                ),
                **_build_curriculum_billing_metrics(estimate=estimate),
                **_build_async_byok_metrics(
                    escrow_id=escrow.id if escrow else None,
                    provider_name=escrow.provider_name if escrow else None,
                    expires_at=escrow.expires_at if escrow else None,
                ),
            },
        )
        job = await job_repo.create(job)

        await db.commit()
        committed = True

        if settings.INGESTION_QUEUE_ENABLED and settings.REDIS_URL:
            from app.services.ingestion.queue import enqueue_ingestion_job

            await enqueue_ingestion_job(
                str(resource.id),
                str(job.id),
                escrow_id=str(escrow.id) if escrow else None,
            )
            logger.info(f"Enqueued ingestion for resource {resource.id}, job {job.id}")
        else:
            background_tasks.add_task(
                run_ingestion_pipeline,
                str(resource.id),
                str(job.id),
                str(escrow.id) if escrow else None,
            )
            logger.info(
                f"Started in-process ingestion for resource {resource.id}, job {job.id}"
            )
    except Exception:
        await db.rollback()
        if committed:
            await _mark_dispatch_failure(
                db=db,
                resource_id=resource_id,
                job_id=job_id,
                owner_user_id=user.id,
                reserved_credits=reserved_credits,
                escrow_id=escrow.id if escrow else None,
                reason="Could not dispatch ingestion job after upload",
            )
        elif reserved_credits > 0:
            await meter.release_ingestion(user.id, str(job_id), reserved_credits)
            await db.commit()
        raise

    return _job_status_payload(job)


@router.get("/status/{job_id}", response_model=IngestionStatusResponse)
async def get_ingestion_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Get the status of an ingestion job."""
    job_repo = IngestionJobRepository(db)
    job = await job_repo.get_by_id(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion job {job_id} not found",
        )

    if job.owner_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return _job_status_payload(job)


@router.post("/retry/{resource_id}", response_model=IngestionStatusResponse)
async def retry_ingestion(
    resource_id: UUID,
    background_tasks: BackgroundTasks,
    use_async_byok: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
    byok: dict = Depends(get_byok_api_key),
):
    """Retry ingestion for an existing resource owned by the authenticated user."""
    resource_repo = ResourceRepository(db)
    resource = await resource_repo.get_by_id(resource_id)

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )

    if resource.owner_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    job_repo = IngestionJobRepository(db)
    latest_job = await job_repo.get_by_resource(resource_id)
    if latest_job and latest_job.status in {"pending", "running"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ingestion is already pending or running for this resource.",
        )

    queue_mode = bool(settings.INGESTION_QUEUE_ENABLED and settings.REDIS_URL)
    byok = byok if isinstance(byok, dict) else {"api_key": None, "api_base_url": None}
    use_async_byok = _normalize_optional_bool(use_async_byok)
    use_async_byok = _resolve_async_byok_request(requested=use_async_byok, byok=byok)
    if queue_mode and not use_async_byok:
        _ensure_async_llm_ready_for_queue()
    await job_repo.expire_stale_active_jobs(max_age_minutes=30 if queue_mode else 5)
    active_jobs = await job_repo.count_active_jobs(include_pending=queue_mode)
    if active_jobs >= settings.INGESTION_MAX_CONCURRENT_JOBS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ingestion queue is full. Please try again shortly.",
            headers={"Retry-After": "120"},
        )

    resource.status = "processing"
    resource.error_message = None

    meter = CreditMeter(db)
    job_id = uuid.uuid4()
    escrow = None
    file_size_bytes = (
        int(
            (
                ((latest_job.metrics or {}).get("billing") or {}).get("file_size_bytes")
                or 0
            )
        )
        if latest_job
        else 0
    )
    estimate = meter.estimate_ingestion_v2(
        file_size_bytes=file_size_bytes,
        filename=resource.filename,
    )
    estimated_credits = 0
    reserved_credits = 0
    uses_platform_credits = settings.CREDITS_ENABLED and not use_async_byok
    if uses_platform_credits:
        estimated_credits = int(estimate["core_upload_credits"])
        reserved = await meter.reserve_for_ingestion(
            user.id, str(job_id), estimated_credits
        )
        if reserved is None:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient credits for upload retry processing. Check your balance in Billing.",
            )
        reserved_credits = reserved

    committed = False
    try:
        if use_async_byok:
            escrow_service = AsyncByokEscrowService(AsyncByokEscrowRepository(db))
            escrow = await escrow_service.create_ingestion_escrow(
                user_id=user.id,
                resource_id=resource.id,
                job_id=job_id,
                byok_api_key=byok["api_key"],
                byok_api_base_url=byok.get("api_base_url"),
            )

        job = IngestionJob(
            id=job_id,
            resource_id=resource.id,
            owner_user_id=user.id,
            status="pending",
            job_kind="core_ingest",
            requested_capability="study_ready",
            scope_type="resource",
            scope_key=str(resource.id),
            progress_percent=0,
            metrics={
                **_build_billing_metrics(
                    uses_platform_credits=uses_platform_credits,
                    estimated_credits=estimated_credits,
                    reserved_credits=reserved_credits,
                    file_size_bytes=file_size_bytes,
                ),
                **_build_curriculum_billing_metrics(estimate=estimate),
                **_build_async_byok_metrics(
                    escrow_id=escrow.id if escrow else None,
                    provider_name=escrow.provider_name if escrow else None,
                    expires_at=escrow.expires_at if escrow else None,
                ),
            },
        )
        job = await job_repo.create(job)

        await db.commit()
        committed = True

        if settings.INGESTION_QUEUE_ENABLED and settings.REDIS_URL:
            from app.services.ingestion.queue import enqueue_ingestion_job

            await enqueue_ingestion_job(
                str(resource.id),
                str(job.id),
                escrow_id=str(escrow.id) if escrow else None,
            )
            logger.info(
                f"Enqueued retry ingestion for resource {resource.id}, job {job.id}"
            )
        else:
            background_tasks.add_task(
                run_ingestion_pipeline,
                str(resource.id),
                str(job.id),
                str(escrow.id) if escrow else None,
            )
            logger.info(
                f"Started in-process retry ingestion for resource {resource.id}, job {job.id}"
            )
    except Exception:
        await db.rollback()
        if committed:
            await _mark_dispatch_failure(
                db=db,
                resource_id=resource.id,
                job_id=job_id,
                owner_user_id=user.id,
                reserved_credits=reserved_credits,
                escrow_id=escrow.id if escrow else None,
                reason="Could not dispatch ingestion retry job",
            )
        elif reserved_credits > 0:
            await meter.release_ingestion(user.id, str(job_id), reserved_credits)
            await db.commit()
        raise

    return _job_status_payload(job)


async def run_ingestion_pipeline(
    resource_id: str, job_id: str, escrow_id: str | None = None
):
    """
    Run the ingestion pipeline for a resource.

    In production, this would be a Celery task.
    """
    from app.db.database import async_session_factory
    from app.db.repositories.async_byok_repo import AsyncByokEscrowRepository
    from app.services.async_byok_escrow import AsyncByokEscrowService
    from app.services.ingestion.pipeline import IngestionPipeline
    from app.services.llm.factory import create_llm_provider
    from app.services.embedding.factory import create_embedding_provider
    from app.services.storage.factory import create_storage_provider

    async with async_session_factory() as db:
        try:
            resource_uuid = UUID(resource_id)
            job_uuid = UUID(job_id)

            job_repo = IngestionJobRepository(db)
            job = await job_repo.get_by_id(job_uuid)
            if job is not None:
                job.status = "running"
                job.current_stage = "worker_pickup"
                if job.started_at is None:
                    job.started_at = datetime.now(timezone.utc)
                await db.commit()

            byok_api_key = None
            byok_api_base_url = None
            escrow_uuid = UUID(escrow_id) if escrow_id else None
            if escrow_uuid is not None:
                escrow_service = AsyncByokEscrowService(AsyncByokEscrowRepository(db))
                resolved = await escrow_service.decrypt_for_ingestion(
                    escrow_id=escrow_uuid,
                    resource_id=resource_uuid,
                    job_id=job_uuid,
                )
                byok_api_key = resolved.api_key
                byok_api_base_url = resolved.api_base_url
                if job is not None:
                    metrics = dict(job.metrics or {})
                    async_byok = dict(metrics.get("async_byok") or {})
                    async_byok["status"] = "decrypted"
                    async_byok["provider_name"] = resolved.provider_name
                    metrics["async_byok"] = async_byok
                    job.metrics = metrics
                    await db.commit()

            llm_provider = create_llm_provider(
                settings,
                task="ontology",
                byok_api_key=byok_api_key,
                byok_api_base_url=byok_api_base_url,
            )
            embedding_provider = create_embedding_provider(settings)
            storage_provider = create_storage_provider(settings)

            # CM-009: Snapshot token counters before pipeline run
            llm_tokens_before = dict(
                getattr(llm_provider, "total_tokens_used", None)
                or {"prompt_tokens": 0, "completion_tokens": 0}
            )

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
                    resource_id=resource_uuid,
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

            # CM-009: Compute actual token usage from measured totals
            llm_tokens_after = dict(
                getattr(llm_provider, "total_tokens_used", None)
                or {"prompt_tokens": 0, "completion_tokens": 0}
            )
            measured_prompt = llm_tokens_after.get(
                "prompt_tokens", 0
            ) - llm_tokens_before.get("prompt_tokens", 0)
            measured_completion = llm_tokens_after.get(
                "completion_tokens", 0
            ) - llm_tokens_before.get("completion_tokens", 0)

            if job and job.owner_user_id:
                billing = _get_billing_state(job)
                reserved_credits = int(billing.get("reserved_credits") or 0)
                if reserved_credits > 0 and billing.get("status") == "reserved":
                    meter = CreditMeter(db)

                    # CM-009: Use operation-based metering with measured token totals
                    if settings.OPERATION_METERING_ENABLED and (
                        measured_prompt > 0 or measured_completion > 0
                    ):
                        op = await meter.create_operation(
                            job.owner_user_id,
                            "ingestion_upload",
                            resource_id=resource_id,
                            selected_model_id=settings.LLM_MODEL_ONTOLOGY
                            or settings.LLM_MODEL,
                            estimate_credits_low=int(
                                billing.get("estimated_credits") or 0
                            ),
                            estimate_credits_high=int(
                                billing.get("estimated_credits") or 0
                            ),
                        )
                        # Ontology usage line (majority of tokens)
                        await meter.append_usage_line(
                            op.id,
                            "ingestion_ontology",
                            settings.LLM_MODEL_ONTOLOGY or settings.LLM_MODEL,
                            input_tokens=int(measured_prompt * 0.6),
                            output_tokens=int(measured_completion * 0.4),
                        )
                        # Enrichment usage line
                        enrichment_model = (
                            settings.LLM_MODEL_ENRICHMENT or settings.LLM_MODEL
                        )
                        await meter.append_usage_line(
                            op.id,
                            "ingestion_enrichment",
                            enrichment_model,
                            input_tokens=int(measured_prompt * 0.4),
                            output_tokens=int(measured_completion * 0.6),
                        )
                        actual_credits = await meter.finalize_operation(
                            job.owner_user_id,
                            op.id,
                            reserved_credits,
                            reference_id=job_id,
                            reference_type="ingestion",
                        )
                    else:
                        # Fallback to estimate-based finalization
                        actual_credits = int(
                            billing.get("actual_credits")
                            or billing.get("estimated_credits")
                            or reserved_credits
                        )
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
                            "measured_prompt_tokens": measured_prompt,
                            "measured_completion_tokens": measured_completion,
                            "status": "finalized",
                        },
                    }
                if escrow_uuid is not None:
                    escrow_service = AsyncByokEscrowService(
                        AsyncByokEscrowRepository(db)
                    )
                    await escrow_service.finalize_job_escrow(
                        escrow_uuid, reason="ingestion_complete", success=True
                    )
                    job.metrics = {
                        **(job.metrics or {}),
                        "async_byok": {
                            **_get_async_byok_state(job),
                            "status": "consumed",
                        },
                    }

            await db.commit()
            logger.info(f"Completed ingestion for resource {resource_id}: {result}")

        except Exception as exc:
            logger.exception(f"Ingestion failed for resource {resource_id}: {exc}")
            await db.rollback()

            async with async_session_factory() as db2:
                job_repo = IngestionJobRepository(db2)
                job = await job_repo.get_by_id(UUID(job_id))
                if job is not None:
                    billing = _get_billing_state(job)
                    curriculum_billing = _get_curriculum_billing_state(job)
                    reserved_credits = int(billing.get("reserved_credits") or 0)
                    if (
                        job.owner_user_id
                        and reserved_credits > 0
                        and billing.get("status") == "reserved"
                    ):
                        meter = CreditMeter(db2)
                        await meter.release_ingestion(
                            job.owner_user_id, job_id, reserved_credits
                        )
                        job.metrics = {
                            **(job.metrics or {}),
                            "billing": {
                                **billing,
                                "status": "released",
                                "release_reason": "worker_failure",
                            },
                        }
                        if (
                            int(curriculum_billing.get("reserved_credits") or 0) > 0
                            and curriculum_billing.get("status") == "reserved"
                        ):
                            await _release_curriculum_reservation(
                                meter,
                                user_id=job.owner_user_id,
                                curriculum_billing=curriculum_billing,
                            )
                            job.metrics = {
                                **(job.metrics or {}),
                                "curriculum_billing": {
                                    **curriculum_billing,
                                    "status": "released",
                                    "release_reason": "worker_failure",
                                },
                            }
                    async_byok = _get_async_byok_state(job)
                    if async_byok.get("escrow_id"):
                        escrow_service = AsyncByokEscrowService(
                            AsyncByokEscrowRepository(db2)
                        )
                        await escrow_service.finalize_job_escrow(
                            UUID(async_byok["escrow_id"]),
                            reason="worker_failure",
                            success=False,
                        )
                        job.metrics = {
                            **(job.metrics or {}),
                            "async_byok": {
                                **async_byok,
                                "status": "deleted",
                            },
                        }
                    job.status = "failed"
                    job.current_stage = "failed"
                    job.error_message = str(exc)[:2000]
                    if job.started_at is None:
                        job.started_at = datetime.now(timezone.utc)
                    job.completed_at = datetime.now(timezone.utc)
                await db2.commit()
