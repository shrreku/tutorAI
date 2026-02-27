import re
from typing import Optional


def append_trace_event(plan: dict, name: str, payload: Optional[dict] = None) -> None:
    """Append stable low-cardinality event metadata for tracing."""
    events = plan.setdefault("__trace_events", [])
    event = {"name": name}
    if payload:
        event.update(payload)
    events.append(event)


def consume_trace_events(plan: dict) -> list[dict]:
    """Return and clear per-turn trace events."""
    events = plan.get("__trace_events", [])
    if "__trace_events" in plan:
        plan.pop("__trace_events", None)
    return events if isinstance(events, list) else []


def detect_question(text: str) -> tuple[bool, Optional[str]]:
    """Detect whether text contains a question and extract the last one.

    Returns (has_question, extracted_question). The extracted question is the
    last sentence ending with '?' and with enough substance to be a real prompt.
    """
    candidates = re.findall(r"[^\n?]*\?", text)
    questions = []
    for q in candidates:
        cleaned = re.sub(r"^[\s\-\*>#\d.]+", "", q).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        alpha_chars = sum(1 for ch in cleaned if ch.isalpha())
        word_count = len(cleaned.split())
        if (
            len(cleaned) >= 15
            and " " in cleaned
            and alpha_chars >= 12
            and word_count >= 4
            and not cleaned.lstrip().startswith("\\")
            and not cleaned.lstrip().startswith("\text")
        ):
            questions.append(cleaned)
    if questions:
        # Prefer the most substantive question; tie-break by most recent.
        best = max(
            enumerate(questions),
            key=lambda pair: (sum(ch.isalpha() for ch in pair[1]), pair[0]),
        )[1]
        return True, best
    return False, None
