from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone


router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    return HealthResponse(status="ok", service="studyagent-api", timestamp=datetime.now(timezone.utc))


@router.get("/health/ready", response_model=HealthResponse)
async def readiness_check():
    """Readiness check - verifies the service is ready to accept traffic."""
    return HealthResponse(status="ready", service="studyagent-api", timestamp=datetime.now(timezone.utc))


@router.get("/health/live", response_model=HealthResponse)
async def liveness_check():
    """Liveness check - verifies the service is running."""
    return HealthResponse(status="alive", service="studyagent-api", timestamp=datetime.now(timezone.utc))
