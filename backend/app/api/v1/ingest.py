import logging
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.db.repositories.resource_repo import ResourceRepository
from app.db.repositories.ingestion_repo import IngestionJobRepository
from app.models.resource import Resource
from app.models.ingestion import IngestionJob
from app.models.resource import default_resource_capabilities
from app.models.session import UserProfile
from app.schemas.api import IngestionStatusResponse, ResourceResponse
from app.services.storage.factory import create_storage_provider
from app.api.deps import require_auth, check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/upload", response_model=IngestionStatusResponse)
async def upload_resource(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    topic: str = Form(default=None),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
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
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Uploads are temporarily disabled")

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
    
    # Save file to storage
    storage = create_storage_provider(settings)
    file_path = await storage.save_file(file_content, file.filename)
    
    # Create resource record
    resource_repo = ResourceRepository(db)
    resource = Resource(
        filename=file.filename,
        owner_user_id=user.id,
        topic=topic,
        status="processing",
        processing_profile="core_only",
        capabilities_json=default_resource_capabilities(),
        file_path_or_uri=file_path,
        uploaded_at=datetime.utcnow(),
    )
    resource = await resource_repo.create(resource)
    
    # Create ingestion job
    job_repo = IngestionJobRepository(db)
    job = IngestionJob(
        resource_id=resource.id,
        owner_user_id=user.id,
        status="pending",
        job_kind="core_ingest",
        requested_capability="study_ready",
        scope_type="resource",
        scope_key=str(resource.id),
        progress_percent=0,
    )
    job = await job_repo.create(job)
    
    # Commit before starting background task (so it can see the records)
    await db.commit()
    
    # Dispatch: durable queue (production) or in-process background task (dev)
    if settings.INGESTION_QUEUE_ENABLED and settings.REDIS_URL:
        from app.services.ingestion.queue import enqueue_ingestion_job
        await enqueue_ingestion_job(str(resource.id), str(job.id))
        logger.info(f"Enqueued ingestion for resource {resource.id}, job {job.id}")
    else:
        background_tasks.add_task(run_ingestion_pipeline, str(resource.id), str(job.id))
        logger.info(f"Started in-process ingestion for resource {resource.id}, job {job.id}")
    
    return IngestionStatusResponse(
        job_id=job.id,
        resource_id=resource.id,
        status=job.status,
        job_kind=job.job_kind,
        requested_capability=job.requested_capability,
        scope_type=job.scope_type,
        scope_key=job.scope_key,
        current_stage=job.current_stage,
        progress_percent=job.progress_percent,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


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
    
    return IngestionStatusResponse(
        job_id=job.id,
        resource_id=job.resource_id,
        status=job.status,
        job_kind=job.job_kind,
        requested_capability=job.requested_capability,
        scope_type=job.scope_type,
        scope_key=job.scope_key,
        current_stage=job.current_stage,
        progress_percent=job.progress_percent,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.post("/retry/{resource_id}", response_model=IngestionStatusResponse)
async def retry_ingestion(
    resource_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
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

    job = IngestionJob(
        resource_id=resource.id,
        owner_user_id=user.id,
        status="pending",
        job_kind="core_ingest",
        requested_capability="study_ready",
        scope_type="resource",
        scope_key=str(resource.id),
        progress_percent=0,
    )
    job = await job_repo.create(job)

    await db.commit()

    if settings.INGESTION_QUEUE_ENABLED and settings.REDIS_URL:
        from app.services.ingestion.queue import enqueue_ingestion_job
        await enqueue_ingestion_job(str(resource.id), str(job.id))
        logger.info(f"Enqueued retry ingestion for resource {resource.id}, job {job.id}")
    else:
        background_tasks.add_task(run_ingestion_pipeline, str(resource.id), str(job.id))
        logger.info(f"Started in-process retry ingestion for resource {resource.id}, job {job.id}")

    return IngestionStatusResponse(
        job_id=job.id,
        resource_id=job.resource_id,
        status=job.status,
        job_kind=job.job_kind,
        requested_capability=job.requested_capability,
        scope_type=job.scope_type,
        scope_key=job.scope_key,
        current_stage=job.current_stage,
        progress_percent=job.progress_percent,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


async def run_ingestion_pipeline(resource_id: str, job_id: str):
    """
    Run the ingestion pipeline for a resource.
    
    In production, this would be a Celery task.
    """
    from app.db.database import async_session_factory
    from app.services.ingestion.pipeline import IngestionPipeline
    from app.services.llm.factory import create_llm_provider
    from app.services.embedding.factory import create_embedding_provider
    from app.services.storage.factory import create_storage_provider
    
    async with async_session_factory() as db:
        try:
            resource_uuid = UUID(resource_id)
            job_uuid = UUID(job_id)
            
            # Create providers
            llm_provider = create_llm_provider(settings)
            embedding_provider = create_embedding_provider(settings)
            storage_provider = create_storage_provider(settings)
            
            # Create and run pipeline
            pipeline = IngestionPipeline(
                db_session=db,
                llm_provider=llm_provider,
                embedding_provider=embedding_provider,
                storage_provider=storage_provider,
            )
            
            result = await pipeline.run(resource_uuid, job_uuid)
            
            await db.commit()
            logger.info(f"Completed ingestion for resource {resource_id}: {result}")
            
        except Exception as e:
            logger.exception(f"Ingestion failed for resource {resource_id}: {e}")
            # Pipeline handles its own error status updates
