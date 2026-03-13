"""
Durable ingestion queue backed by Redis.

When ``INGESTION_QUEUE_ENABLED=true`` (and ``REDIS_URL`` is set), ingestion
jobs are pushed to a Redis list instead of running in-process via FastAPI
``BackgroundTasks``.  A separate worker process (``worker.py``) consumes and
executes the jobs.

When ``INGESTION_QUEUE_ENABLED=false`` the module exposes a thin no-op
interface so the rest of the code can remain queue-agnostic.
"""

import json
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

QUEUE_KEY = "studyagent:ingestion:jobs"
DLQ_KEY = "studyagent:ingestion:dlq"

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Return a shared async Redis client (lazy-initialised)."""
    global _redis_client
    if _redis_client is None:
        if not settings.REDIS_URL:
            raise RuntimeError(
                "REDIS_URL is not configured but queue operation was requested"
            )
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def enqueue_ingestion_job(
    resource_id: str, job_id: str, *, escrow_id: str | None = None
) -> None:
    """Push an ingestion job onto the durable Redis queue."""
    r = await get_redis()
    payload = json.dumps(
        {"resource_id": resource_id, "job_id": job_id, "escrow_id": escrow_id}
    )
    await r.rpush(QUEUE_KEY, payload)
    logger.info(f"Enqueued ingestion job {job_id} for resource {resource_id}")


async def queued_job_ids() -> set[str]:
    """Return the job ids currently waiting in the Redis queue."""
    r = await get_redis()
    payloads = await r.lrange(QUEUE_KEY, 0, -1)
    job_ids: set[str] = set()
    for payload in payloads:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed ingestion queue payload during recovery")
            continue
        job_id = data.get("job_id") if isinstance(data, dict) else None
        if job_id:
            job_ids.add(str(job_id))
    return job_ids


async def dequeue_ingestion_job(timeout: int = 5) -> Optional[dict]:
    """Block-pop the next job from the queue.  Returns ``None`` on timeout."""
    r = await get_redis()
    result = await r.blpop(QUEUE_KEY, timeout=timeout)
    if result is None:
        return None
    _, payload = result
    return json.loads(payload)


async def send_to_dlq(job_payload: dict, error: str) -> None:
    """Move a failed job to the dead-letter queue for inspection."""
    r = await get_redis()
    job_payload["error"] = error
    await r.rpush(DLQ_KEY, json.dumps(job_payload))
    logger.warning(f"Moved job {job_payload.get('job_id')} to DLQ: {error}")


async def queue_depth() -> int:
    """Return the current number of pending jobs."""
    r = await get_redis()
    return await r.llen(QUEUE_KEY)


async def dlq_depth() -> int:
    """Return the current number of dead-letter jobs."""
    r = await get_redis()
    return await r.llen(DLQ_KEY)
