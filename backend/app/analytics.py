"""
Analytics foundation (PROD-014).

Thin wrapper around PostHog for server-side event capture.
No-ops gracefully when POSTHOG_ENABLED is false or the package is missing.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_posthog_client: Any | None = None
_initialized = False


def _ensure_client() -> Any | None:
    global _posthog_client, _initialized
    if _initialized:
        return _posthog_client
    _initialized = True

    from app.config import settings

    if not settings.POSTHOG_ENABLED or not settings.POSTHOG_API_KEY:
        logger.info("PostHog disabled or API key not set – analytics no-op")
        return None

    try:
        import posthog

        posthog.project_api_key = settings.POSTHOG_API_KEY
        posthog.host = settings.POSTHOG_HOST
        posthog.debug = False
        posthog.on_error = lambda e, _batch: logger.warning("PostHog error: %s", e)
        _posthog_client = posthog
        logger.info("PostHog analytics initialised")
        return _posthog_client
    except ImportError:
        logger.warning("posthog package not installed – analytics no-op")
        return None
    except Exception:
        logger.exception("Failed to initialise PostHog")
        return None


def capture(
    distinct_id: str,
    event: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Capture an analytics event. No-ops if PostHog is not configured."""
    client = _ensure_client()
    if client is None:
        return
    try:
        client.capture(distinct_id, event, properties=properties or {})
    except Exception:
        logger.debug("Failed to capture analytics event %s", event, exc_info=True)


def identify(
    distinct_id: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Identify a user. No-ops if PostHog is not configured."""
    client = _ensure_client()
    if client is None:
        return
    try:
        client.identify(distinct_id, properties=properties or {})
    except Exception:
        logger.debug("Failed to identify user %s", distinct_id, exc_info=True)


def shutdown() -> None:
    """Flush and shutdown PostHog client."""
    global _posthog_client, _initialized
    if _posthog_client is not None:
        try:
            _posthog_client.shutdown()
        except Exception:
            pass
    _posthog_client = None
    _initialized = False
