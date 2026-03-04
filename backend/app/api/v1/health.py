from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional

from app.config import settings


router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime
    queue_depth: Optional[int] = None
    dlq_depth: Optional[int] = None


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    return HealthResponse(status="ok", service="studyagent-api", timestamp=datetime.now(timezone.utc))


@router.get("/health/ready", response_model=HealthResponse)
async def readiness_check():
    """Readiness check - verifies the service is ready to accept traffic."""
    extra = {}
    if settings.INGESTION_QUEUE_ENABLED and settings.REDIS_URL:
        try:
            from app.services.ingestion.queue import queue_depth, dlq_depth
            extra["queue_depth"] = await queue_depth()
            extra["dlq_depth"] = await dlq_depth()
        except Exception:
            pass
    return HealthResponse(status="ready", service="studyagent-api", timestamp=datetime.now(timezone.utc), **extra)


@router.get("/health/live", response_model=HealthResponse)
async def liveness_check():
    """Liveness check - verifies the service is running."""
    return HealthResponse(status="alive", service="studyagent-api", timestamp=datetime.now(timezone.utc))
