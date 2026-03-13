"""
Langfuse v3 tracing utilities for the StudyAgent tutoring pipeline.

Architecture:
  - Uses Langfuse Python SDK v3 (OpenTelemetry-based)
  - `from langfuse.openai import AsyncOpenAI` auto-instruments all LLM calls
  - `@observe()` decorator on agent methods creates nested spans
  - `start_as_current_observation()` context manager for turn-level traces
  - `propagate_attributes()` propagates session_id / user_id to children
  - Scores attached via `create_score()` or `span.score_trace()`

Trace hierarchy (objectives & steps are the working units):
  tutor-turn                                  ← root span (session_id, turn_id)
    ├─ turn.load_state                         ← session + pointer load
    ├─ curriculum-init (first turn only)      ← plan generation
    │   └─ curriculum-planner (@observe)
    │       └─ <generation>
    ├─ objective                               ← objective span (objective_id, concepts, progress)
    │   ├─ step.execute                        ← step span (step_index, target_concepts)
    │   │   ├─ evaluate-response              ← evaluator (if awaiting)
    │   │   │   └─ evaluator-agent (@observe)
    │   │   │       └─ <generation>
    │   │   ├─ policy-decision                ← policy agent
    │   │   ├─ policy-guards                  ← guard metadata span
    │   │   │   └─ policy-agent (@observe)
    │   │   │       └─ <generation>
    │   │   ├─ knowledge-retrieval            ← RAG retrieval
    │   │   ├─ generate-response              ← tutor agent
    │   │   │   └─ tutor-agent (@observe)
    │   │   │       └─ <generation>
    │   │   ├─ safety-check
    │   │   │   └─ safety-critic (@observe)
    │   │       └─ <generation>
    │   └─ progression                        ← step/objective transition
    ├─ turn.persist                           ← db persistence
    └─ turn.score                             ← scoring
"""

import logging
import hashlib
import os
import re
from typing import Any, Optional

from langfuse import Langfuse, get_client

from app.config import settings

logger = logging.getLogger(__name__)


MAX_TRACE_TEXT = 180
MAX_TRACE_LIST_ITEMS = 8
MAX_TRACE_DICT_ITEMS = 20


def is_detailed_tracing_enabled() -> bool:
    """Return whether verbose/manual Langfuse stage spans should be emitted."""
    mode = (
        (os.getenv("LANGFUSE_TRACE_MODE") or settings.LANGFUSE_TRACE_MODE or "simple")
        .strip()
        .lower()
    )
    return mode in {"detailed", "verbose", "full"}


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def init_langfuse() -> Optional[Langfuse]:
    """
    Initialise the Langfuse singleton.

    The SDK reads LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and
    LANGFUSE_BASE_URL from environment variables automatically.
    Calling Langfuse() here ensures the singleton is created once.
    Returns the client or None if credentials are missing.
    """
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        logger.info("Langfuse credentials not configured – tracing disabled")
        return None
    try:
        client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            base_url=settings.LANGFUSE_BASE_URL or "https://cloud.langfuse.com",
        )
        if client.auth_check():
            logger.info("Langfuse v3 SDK initialised and authenticated")
        else:
            logger.warning("Langfuse auth_check failed – traces may not appear")
        return client
    except Exception as e:
        logger.warning(f"Langfuse init failed: {e}")
        return None


def get_langfuse_client() -> Optional[Langfuse]:
    """Return the Langfuse singleton (lazy init via get_client)."""
    try:
        return get_client()
    except Exception:
        return None


def flush_langfuse():
    """Flush pending events. Call on shutdown or after critical traces."""
    try:
        client = get_langfuse_client()
        if client:
            client.flush()
    except Exception as e:
        logger.debug(f"Langfuse flush error: {e}")


def redact_text_for_trace(text: Optional[str], max_chars: int = MAX_TRACE_TEXT) -> str:
    """Redact obvious PII patterns and cap text length for trace metadata."""
    if not text:
        return ""

    cleaned = str(text)
    cleaned = re.sub(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted-email]", cleaned
    )
    cleaned = re.sub(r"\b(?:\+?\d[\d\-\s().]{7,}\d)\b", "[redacted-phone]", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars]}...[truncated:{len(cleaned) - max_chars}]"


def normalize_trace_metadata(value: Any) -> Any:
    """Normalize metadata to low-cardinality, size-bounded structures."""
    if isinstance(value, str):
        return redact_text_for_trace(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [normalize_trace_metadata(v) for v in value[:MAX_TRACE_LIST_ITEMS]]
    if isinstance(value, tuple):
        return [normalize_trace_metadata(v) for v in list(value)[:MAX_TRACE_LIST_ITEMS]]
    if isinstance(value, dict):
        normalized = {}
        for idx, (k, v) in enumerate(value.items()):
            if idx >= MAX_TRACE_DICT_ITEMS:
                break
            normalized[str(k)[:64]] = normalize_trace_metadata(v)
        return normalized
    return redact_text_for_trace(str(value))


def should_sample_trace(key: str, sample_rate: float) -> bool:
    """Deterministic sampling gate for high-volume tracing paths."""
    if sample_rate >= 1.0:
        return True
    if sample_rate <= 0.0:
        return False
    digest = hashlib.sha256((key or "").encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return bucket <= sample_rate


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def score_trace(
    trace_id: str,
    name: str,
    value: float,
    comment: Optional[str] = None,
    data_type: str = "NUMERIC",
):
    """Attach a numeric score to a trace by ID."""
    try:
        client = get_langfuse_client()
        if client:
            client.create_score(
                trace_id=trace_id,
                name=name,
                value=value,
                data_type=data_type,
                comment=comment,
            )
    except Exception as e:
        logger.debug(f"Langfuse score '{name}' failed: {e}")


def score_trace_categorical(
    trace_id: str,
    name: str,
    value: str,
    comment: Optional[str] = None,
):
    """Attach a categorical score to a trace by ID."""
    try:
        client = get_langfuse_client()
        if client:
            client.create_score(
                trace_id=trace_id,
                name=name,
                value=value,
                data_type="CATEGORICAL",
                comment=comment,
            )
    except Exception as e:
        logger.debug(f"Langfuse categorical score '{name}' failed: {e}")
