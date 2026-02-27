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
from app.schemas.api import IngestionStatusResponse, ResourceResponse
from app.services.storage.factory import create_storage_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/upload", response_model=IngestionStatusResponse)
async def upload_resource(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    topic: str = Form(default=None),
    db: AsyncSession = Depends(get_db),
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
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported",
        )
    
    # Read file content
    file_content = await file.read()
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
        topic=topic,
        status="processing",
        file_path_or_uri=file_path,
        uploaded_at=datetime.utcnow(),
    )
    resource = await resource_repo.create(resource)
    
    # Create ingestion job
    job_repo = IngestionJobRepository(db)
    job = IngestionJob(
        resource_id=resource.id,
        status="pending",
        progress_percent=0,
    )
    job = await job_repo.create(job)
    
    # Commit before starting background task (so it can see the records)
    await db.commit()
    
    # Start background ingestion
    # Note: In production, this would be a Celery task or similar
    background_tasks.add_task(run_ingestion_pipeline, str(resource.id), str(job.id))
    
    logger.info(f"Started ingestion for resource {resource.id}, job {job.id}")
    
    return IngestionStatusResponse(
        job_id=job.id,
        resource_id=resource.id,
        status=job.status,
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
):
    """Get the status of an ingestion job."""
    job_repo = IngestionJobRepository(db)
    job = await job_repo.get_by_id(job_id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion job {job_id} not found",
        )
    
    return IngestionStatusResponse(
        job_id=job.id,
        resource_id=job.resource_id,
        status=job.status,
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
