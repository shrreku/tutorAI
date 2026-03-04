import json
import logging
from typing import Any, Mapping

logger = logging.getLogger("notebook.telemetry")


def emit_notebook_event(
    event: str,
    *,
    user_id: str,
    notebook_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    """Emit a structured notebook telemetry event via application logs."""
    payload = {
        "event": event,
        "user_id": user_id,
        "notebook_id": notebook_id,
        "metadata": dict(metadata or {}),
    }
    logger.info(json.dumps(payload, sort_keys=True))
