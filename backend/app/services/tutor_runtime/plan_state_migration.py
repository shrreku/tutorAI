from __future__ import annotations

from copy import deepcopy
from typing import Any


PLAN_STATE_VERSION = 3


def migrate_plan_state_to_v3(plan_state: dict[str, Any] | None) -> dict[str, Any]:
    """Return a v3-normalized copy of plan_state for runtime reads.

    Track E cutover enforces v3-only semantics. Legacy runtime versions are now
    rejected instead of silently upgraded.
    """
    plan = deepcopy(plan_state or {})
    version = plan.get("version")

    if version not in (None, PLAN_STATE_VERSION):
        raise ValueError(
            f"Unsupported legacy plan_state version '{version}'. "
            "Runtime requires version 3 after migration cutover."
        )

    # Enforce canonical runtime version on read so downstream mutators only
    # operate on one contract.
    plan["version"] = PLAN_STATE_VERSION
    return plan
