from __future__ import annotations

from typing import Any


def _stringify_value(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            if item is None:
                continue
            items.append(f"{key}={_stringify_value(item)}")
        return ", ".join(items) if items else "N/A"
    if isinstance(value, (list, tuple, set)):
        items = [str(item) for item in value if item is not None]
        return ", ".join(items) if items else "N/A"
    return str(value)


def format_personalization_block(snapshot: dict[str, Any] | None) -> str:
    """Render a compact prompt block for learner personalization."""
    if not snapshot:
        return "LEARNER PREFERENCES: (none provided)"

    order = [
        "pace",
        "depth",
        "tutoring_style",
        "hint_level",
        "language",
        "purpose",
        "urgency",
        "study_pace",
        "study_depth",
        "practice_intensity",
        "exam_context",
        "time_budget_minutes",
        "today_goal",
        "interaction_style",
        "confidence",
        "want_hints",
        "want_examples",
    ]
    lines: list[str] = []
    for key in order:
        if key in snapshot and snapshot.get(key) is not None:
            lines.append(f"  {key}: {_stringify_value(snapshot.get(key))}")

    remaining_keys = [
        key for key in snapshot.keys() if key not in set(order)
    ]
    for key in remaining_keys:
        value = snapshot.get(key)
        if value is not None:
            lines.append(f"  {key}: {_stringify_value(value)}")

    return "LEARNER PREFERENCES:\n" + ("\n".join(lines) if lines else "  (none provided)")