import json
import logging
from typing import Any, Mapping

logger = logging.getLogger("billing.telemetry")


def emit_billing_event(
    event: str,
    *,
    user_id: str,
    operation_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    """Emit a structured billing telemetry event via application logs.

    Events:
      billing.operation.created
      billing.operation.reserved
      billing.operation.finalized
      billing.operation.released
      billing.usage_line.appended
      billing.health.degraded
      billing.health.disabled
      billing.health.recovered
      billing.health.rerouted
    """
    payload = {
        "event": event,
        "user_id": user_id,
        "operation_id": operation_id,
        "metadata": dict(metadata or {}),
    }
    logger.info(json.dumps(payload, sort_keys=True))


# ---------------------------------------------------------------------------
# CM-018: Typed observability helpers for dashboards & alerts
# ---------------------------------------------------------------------------

def emit_cost_drift(
    *,
    user_id: str,
    operation_id: str,
    operation_type: str,
    estimated_credits: float,
    actual_credits: float,
    model_id: str,
) -> None:
    """Log when finalised cost deviates significantly from estimate."""
    drift_pct = (
        ((actual_credits - estimated_credits) / estimated_credits * 100)
        if estimated_credits > 0
        else 0.0
    )
    emit_billing_event(
        "billing.metric.cost_drift",
        user_id=user_id,
        operation_id=operation_id,
        metadata={
            "operation_type": operation_type,
            "model_id": model_id,
            "estimated_credits": estimated_credits,
            "actual_credits": actual_credits,
            "drift_pct": round(drift_pct, 2),
        },
    )


def emit_reroute(
    *,
    user_id: str,
    operation_id: str | None = None,
    task: str,
    selected_model_id: str,
    routed_model_id: str,
    reason: str,
) -> None:
    """Log a model reroute event for alerting on fallback spikes."""
    emit_billing_event(
        "billing.metric.model_reroute",
        user_id=user_id,
        operation_id=operation_id,
        metadata={
            "task": task,
            "selected_model_id": selected_model_id,
            "routed_model_id": routed_model_id,
            "reason": reason,
        },
    )


def emit_cooldown_event(
    *,
    model_id: str,
    task: str,
    action: str,  # "entered" | "cleared" | "auto_recovered"
    error_rate: float | None = None,
    cooldown_until: str | None = None,
) -> None:
    """Log cooldown lifecycle events for spike alerting."""
    emit_billing_event(
        f"billing.metric.cooldown.{action}",
        user_id="system",
        metadata={
            "model_id": model_id,
            "task": task,
            "action": action,
            "error_rate": error_rate,
            "cooldown_until": cooldown_until,
        },
    )


def emit_estimation_quality(
    *,
    operation_type: str,
    model_id: str,
    estimated_low: float,
    estimated_high: float,
    actual: float,
) -> None:
    """Log estimate vs. actual for calibration dashboards."""
    within_range = estimated_low <= actual <= estimated_high
    emit_billing_event(
        "billing.metric.estimation_quality",
        user_id="system",
        metadata={
            "operation_type": operation_type,
            "model_id": model_id,
            "estimated_low": estimated_low,
            "estimated_high": estimated_high,
            "actual": actual,
            "within_range": within_range,
        },
    )
