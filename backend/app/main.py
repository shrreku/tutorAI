import uuid
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.v1.router import api_router
from app.schemas.common import ErrorResponse
from app.services.tracing import init_langfuse, flush_langfuse


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
# Suppress noisy libraries
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def _validate_auth_config() -> None:
    """Fail fast when auth is enabled with an unsafe JWT signing key."""
    if not settings.AUTH_ENABLED or not settings.AUTH_ENFORCE_STRONG_SECRET:
        return

    secret = (settings.AUTH_SECRET_KEY or "").strip()
    lowered = secret.lower()
    weak_markers = (
        "your-secret-key",
        "change-in-production",
        "changeme",
        "replace-me",
    )

    if len(secret) < settings.AUTH_SECRET_MIN_LENGTH or any(marker in lowered for marker in weak_markers):
        raise RuntimeError(
            "AUTH_SECRET_KEY is weak or placeholder while AUTH_ENABLED=true. "
            "Set a high-entropy secret (>=32 chars)."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting StudyAgent API...")
    _validate_auth_config()
    # Initialise Langfuse singleton (reads env vars, runs auth_check)
    lf = init_langfuse()
    logger.info(f"Langfuse enabled: {lf is not None}")
    logger.info(
        "Neo4j enabled: %s (configured=%s)",
        settings.NEO4J_ENABLED,
        bool(settings.NEO4J_URI),
    )
    yield
    logger.info("Shutting down StudyAgent API...")
    flush_langfuse()


app = FastAPI(
    title="StudyAgent API",
    description="AI-powered tutoring system with grounded, adaptive instruction",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware — allow local dev and production frontend origins
_allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
# In production, add your deployed frontend URL via environment variable
import os as _os
_prod_origin = _os.getenv("CORS_ALLOWED_ORIGIN")
if _prod_origin:
    _allowed_origins.append(_prod_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import time


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attach X-Request-Id and measure latency for observability."""
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    request.state.request_id = request_id
    start = time.perf_counter()

    response = await call_next(request)

    latency_ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Response-Time-Ms"] = str(latency_ms)

    # Structured log line for aggregation / dashboards
    logger.info(
        "request_complete path=%s method=%s status=%s latency_ms=%d request_id=%s",
        request.url.path,
        request.method,
        response.status_code,
        latency_ms,
        request_id,
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler returning canonical ErrorResponse."""
    request_id = getattr(request.state, "request_id", None)
    logger.exception(f"Unhandled exception [request_id={request_id}]: {exc}")
    
    error_response = ErrorResponse(
        error="Internal server error",
        detail=str(exc) if settings.AUTH_ENABLED is False else None,
        code="INTERNAL_ERROR",
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump(),
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle ValueError as 400 Bad Request."""
    request_id = getattr(request.state, "request_id", None)
    
    error_response = ErrorResponse(
        error="Bad request",
        detail=str(exc),
        code="BAD_REQUEST",
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=error_response.model_dump(),
    )


# Include API router
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Welcome to StudyAgent API", "docs": "/docs"}
