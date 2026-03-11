"""Model-task health tracking and cooldown routing (CM-010).

Tracks per model-task health state. On repeated failures, puts model-task
pairs into cooldown so fallback models are used instead.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.metering_repo import MeteringRepository
from app.services.telemetry.billing_events import emit_billing_event, emit_cooldown_event

logger = logging.getLogger(__name__)


class ModelHealthService:
    """Tracks and reacts to model-task health state."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = MeteringRepository(db)

    async def record_success(self, model_id: str, task_type: str) -> None:
        """Record a successful model call for a task."""
        if not settings.MODEL_TASK_HEALTH_ROUTING_ENABLED:
            return
        health = await self.repo.get_or_create_health(model_id, task_type)
        health.consecutive_errors = 0
        health.last_success_at = datetime.now(timezone.utc)
        # Recovery: if we were degraded and got enough successes, heal
        if health.status == "degraded":
            health.status = "healthy"
            health.cooldown_until = None
            logger.info("Model-task %s/%s recovered to healthy", model_id, task_type)
        self.db.add(health)
        await self.db.flush()

    async def record_error(
        self,
        model_id: str,
        task_type: str,
        error_code: str = "unknown",
        error_summary: str = "",
    ) -> None:
        """Record a failed model call and potentially trigger cooldown."""
        if not settings.MODEL_TASK_HEALTH_ROUTING_ENABLED:
            return
        health = await self.repo.get_or_create_health(model_id, task_type)
        now = datetime.now(timezone.utc)
        health.consecutive_errors += 1
        health.last_error_at = now
        health.last_error_code = error_code
        health.last_error_summary = error_summary[:500] if error_summary else None

        threshold = settings.HEALTH_CONSECUTIVE_ERROR_THRESHOLD
        if health.consecutive_errors >= threshold and health.status == "healthy":
            health.status = "degraded"
            health.cooldown_until = now + timedelta(seconds=settings.HEALTH_COOLDOWN_SECONDS)
            logger.warning(
                "Model-task %s/%s entered cooldown until %s after %d consecutive errors",
                model_id, task_type, health.cooldown_until, health.consecutive_errors,
            )
            emit_billing_event(
                "billing.health.degraded", user_id="system",
                metadata={"model_id": model_id, "task_type": task_type, "errors": health.consecutive_errors},
            )
            emit_cooldown_event(
                model_id=model_id, task=task_type, action="entered",
                error_rate=float(health.consecutive_errors),
                cooldown_until=health.cooldown_until.isoformat() if health.cooldown_until else None,
            )
        elif health.consecutive_errors >= threshold * 2:
            health.status = "disabled"
            health.cooldown_until = None
            logger.error(
                "Model-task %s/%s disabled after %d consecutive errors",
                model_id, task_type, health.consecutive_errors,
            )
            emit_billing_event(
                "billing.health.disabled", user_id="system",
                metadata={"model_id": model_id, "task_type": task_type, "errors": health.consecutive_errors},
            )

        self.db.add(health)
        await self.db.flush()

    async def is_healthy(self, model_id: str, task_type: str) -> bool:
        """Check if a model-task pair is available for routing."""
        if not settings.MODEL_TASK_HEALTH_ROUTING_ENABLED:
            return True
        health = await self.repo.get_health(model_id, task_type)
        if health is None:
            return True  # no record = healthy
        if health.status in ("disabled", "manual_only"):
            return False
        if health.status == "degraded" and health.cooldown_until:
            if datetime.now(timezone.utc) < health.cooldown_until:
                return False
            # Cooldown expired — let it try again
        return True

    async def resolve_model(
        self,
        task_type: str,
        user_preferred_model: Optional[str] = None,
    ) -> tuple[str, Optional[str]]:
        """Resolve the model to use for a task, considering health state.

        Returns (model_id, reroute_reason).
        If reroute_reason is None, the default/preferred model was used.
        """
        assignment = await self.repo.get_assignment(task_type)
        if assignment is None:
            return (settings.LLM_MODEL, None)

        # Determine candidate order
        candidates = []
        if user_preferred_model and assignment.user_override_allowed:
            allowed = assignment.allowed_model_ids or []
            if user_preferred_model in allowed:
                candidates.append(user_preferred_model)
        candidates.append(assignment.default_model_id)
        for fb in (assignment.fallback_model_ids or []):
            if fb not in candidates:
                candidates.append(fb)

        for model_id in candidates:
            if await self.is_healthy(model_id, task_type):
                reason = None
                if model_id != candidates[0]:
                    reason = f"Rerouted from {candidates[0]} due to health state"
                return (model_id, reason)

        # All candidates unhealthy — use default anyway with warning
        logger.error("All models unhealthy for task %s, falling back to default", task_type)
        return (assignment.default_model_id, "All fallbacks exhausted; using default despite health state")

    async def clear_cooldown(self, model_id: str, task_type: str, reason: str = "") -> None:
        """Admin: clear cooldown for a model-task pair."""
        health = await self.repo.get_or_create_health(model_id, task_type)
        health.status = "healthy"
        health.cooldown_until = None
        health.consecutive_errors = 0
        health.manual_override_reason = reason or "Admin cleared cooldown"
        self.db.add(health)
        await self.db.flush()

    async def disable_model_task(self, model_id: str, task_type: str, reason: str = "") -> None:
        """Admin: disable a specific model for a specific task."""
        health = await self.repo.get_or_create_health(model_id, task_type)
        health.status = "disabled"
        health.manual_override_reason = reason or "Admin disabled"
        self.db.add(health)
        await self.db.flush()

    async def enable_model_task(self, model_id: str, task_type: str, reason: str = "") -> None:
        """Admin: re-enable a model-task pair."""
        health = await self.repo.get_or_create_health(model_id, task_type)
        health.status = "healthy"
        health.cooldown_until = None
        health.consecutive_errors = 0
        health.manual_override_reason = reason or "Admin enabled"
        self.db.add(health)
        await self.db.flush()
