from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.config import settings
from app.db.database import async_session_factory
from app.services.llm.factory import get_missing_platform_llm_config


router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime
    queue_depth: Optional[int] = None
    dlq_depth: Optional[int] = None
    dependencies: Optional[dict[str, str]] = None


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    return HealthResponse(
        status="ok", service="studyagent-api", timestamp=datetime.now(timezone.utc)
    )


@router.get("/health/ready", response_model=HealthResponse)
async def readiness_check():
    """Readiness check for serving traffic with required dependencies."""
    dependencies = {"database": "unknown"}

    try:
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        dependencies["database"] = "ready"
    except Exception as exc:
        dependencies["database"] = "unavailable"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "service": "studyagent-api",
                "dependencies": dependencies,
                "reason": f"database check failed: {exc}",
            },
        ) from exc

    extra = {"dependencies": dependencies}
    if settings.INGESTION_QUEUE_ENABLED and settings.REDIS_URL:
        try:
            from app.services.ingestion.queue import dlq_depth, get_redis, queue_depth

            redis = await get_redis()
            await redis.ping()
            dependencies["redis"] = "ready"
            extra["queue_depth"] = await queue_depth()
            extra["dlq_depth"] = await dlq_depth()
        except Exception as exc:
            dependencies["redis"] = "unavailable"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "status": "not_ready",
                    "service": "studyagent-api",
                    "dependencies": dependencies,
                    "reason": f"redis check failed: {exc}",
                },
            ) from exc

        missing_llm = get_missing_platform_llm_config(settings, task="ontology")
        if missing_llm:
            dependencies["async_llm"] = "required_but_unconfigured"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "status": "not_ready",
                    "service": "studyagent-api",
                    "dependencies": dependencies,
                    "reason": (
                        "queue mode requires platform-managed LLM credentials for async ingestion; "
                        f"missing {', '.join(missing_llm)}"
                    ),
                },
            )
        dependencies["async_llm"] = "ready"
    elif settings.INGESTION_QUEUE_ENABLED:
        dependencies["redis"] = "required_but_unconfigured"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "service": "studyagent-api",
                "dependencies": dependencies,
                "reason": "queue mode is enabled but REDIS_URL is not configured",
            },
        )
    else:
        dependencies["redis"] = "optional_disabled"
        dependencies["async_llm"] = "optional_disabled"

    return HealthResponse(
        status="ready",
        service="studyagent-api",
        timestamp=datetime.now(timezone.utc),
        **extra,
    )


@router.get("/health/live", response_model=HealthResponse)
async def liveness_check():
    """Liveness check - verifies the service is running."""
    return HealthResponse(
        status="alive", service="studyagent-api", timestamp=datetime.now(timezone.utc)
    )


class VersionResponse(BaseModel):
    version: str
    service: str
    environment: str
    features: dict[str, bool]


@router.get("/health/version", response_model=VersionResponse)
async def version_info():
    """Return build version and enabled feature flags for deploy verification."""
    return VersionResponse(
        version="0.2.0",
        service="studyagent-api",
        environment=settings.SENTRY_ENVIRONMENT,
        features={
            "notebooks": True,
            "workspace_v2": settings.FF_WORKSPACE_V2_ENABLED,
            "active_learning": settings.FF_ACTIVE_LEARNING_ENABLED,
            "artifact_generation": settings.FF_ARTIFACT_GENERATION_ENABLED,
            "credits": settings.CREDITS_ENABLED,
            "byok": settings.BYOK_ENABLED,
            "queue": settings.INGESTION_QUEUE_ENABLED,
            "sentry": bool(settings.SENTRY_DSN),
            "otel": settings.OTEL_ENABLED,
            "posthog": settings.POSTHOG_ENABLED,
        },
    )
