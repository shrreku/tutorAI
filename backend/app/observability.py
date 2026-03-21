"""
Observability foundation (PROD-013).

Initialises Sentry error tracking and OpenTelemetry tracing.
All integrations are gated behind env-var flags so the app boots
cleanly when no DSN / endpoint is configured.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Configure Sentry SDK if SENTRY_DSN is set."""
    from app.config import settings

    if not settings.SENTRY_DSN:
        logger.info("Sentry DSN not configured – skipping Sentry init")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
            send_default_pii=False,
        )
        logger.info("Sentry initialised (env=%s)", settings.SENTRY_ENVIRONMENT)
    except ImportError:
        logger.warning("sentry-sdk not installed – skipping Sentry init")
    except Exception:
        logger.exception("Failed to initialise Sentry")


def init_otel(app: "FastAPI") -> None:
    """Configure OpenTelemetry tracing if OTEL_ENABLED is true."""
    from app.config import settings

    if not settings.OTEL_ENABLED:
        logger.info("OpenTelemetry disabled – skipping OTEL init")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
        provider = TracerProvider(resource=resource)

        if settings.OTEL_EXPORTER_ENDPOINT:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_ENDPOINT)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info(
                "OTEL exporter configured -> %s", settings.OTEL_EXPORTER_ENDPOINT
            )

        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry initialised (service=%s)", settings.OTEL_SERVICE_NAME)
    except ImportError:
        logger.warning("opentelemetry packages not installed – skipping OTEL init")
    except Exception:
        logger.exception("Failed to initialise OpenTelemetry")


def setup_observability(app: "FastAPI") -> None:
    """One-call entry point used by main.py startup."""
    init_sentry()
    init_otel(app)
