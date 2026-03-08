import hashlib
import json
import re
from collections import Counter
from typing import Any

STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "into", "your", "have", "will", "are",
    "was", "were", "their", "there", "about", "which", "when", "where", "then", "than", "them",
    "into", "through", "chapter", "section", "page", "pages", "figure", "table", "using", "used",
    "example", "definition", "practice", "exercise", "introduction", "summary", "conclusion",
}


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text or "")]


def _normalize_heading(section: Any) -> str | None:
    if isinstance(section, dict):
        heading = section.get("heading") or section.get("title")
    else:
        heading = getattr(section, "heading", None) or getattr(section, "title", None)
    if not heading:
        return None
    normalized = " ".join(str(heading).split())
    return normalized[:160] if normalized else None


def _detect_document_type(filename: str, headings: list[str], keyword_counts: Counter[str]) -> str:
    lowered_name = (filename or "").lower()
    heading_blob = " ".join(headings).lower()
    if any(token in lowered_name for token in ["slide", "ppt", "deck"]) or "agenda" in heading_blob:
        return "slides"
    if any(token in lowered_name for token in ["worksheet", "assignment"]) or keyword_counts.get("exercise", 0) >= 2:
        return "worksheet"
    if any(token in lowered_name for token in ["exam", "test", "quiz"]) or keyword_counts.get("question", 0) >= 3:
        return "assessment"
    if keyword_counts.get("theorem", 0) or keyword_counts.get("proof", 0):
        return "technical_notes"
    return "study_notes"


def build_resource_profile(
    *,
    filename: str,
    topic: str | None,
    sections: list[Any],
    chunks: list[Any],
    chunking_metadata: dict | None = None,
) -> dict:
    """Build a deterministic lightweight understanding artifact for a resource."""
    headings = [heading for section in sections if (heading := _normalize_heading(section))]
    heading_counts = Counter(_tokenize(" ".join(headings)))

    body_counter: Counter[str] = Counter()
    pedagogy_signals = Counter()
    page_numbers: list[int] = []

    for chunk in chunks[:32]:
        text = getattr(chunk, "text", "") or ""
        tokens = [token for token in _tokenize(text) if token not in STOPWORDS]
        body_counter.update(tokens[:80])

        lowered = text.lower()
        if "definition" in lowered:
            pedagogy_signals["definition"] += 1
        if "example" in lowered:
            pedagogy_signals["example"] += 1
        if "exercise" in lowered or "practice" in lowered:
            pedagogy_signals["exercise"] += 1
        if "theorem" in lowered:
            pedagogy_signals["theorem"] += 1
        if "proof" in lowered:
            pedagogy_signals["proof"] += 1

        for page_value in (getattr(chunk, "page_start", None), getattr(chunk, "page_end", None)):
            if isinstance(page_value, int):
                page_numbers.append(page_value)

    keyword_counts = heading_counts + body_counter
    top_keywords = [
        token
        for token, _ in keyword_counts.most_common(12)
        if token not in STOPWORDS and len(token) > 2
    ][:8]

    document_type = _detect_document_type(filename, headings, keyword_counts)
    payload = {
        "artifact_kind": "resource_profile",
        "artifact_version": "1.0",
        "filename": filename,
        "topic": topic,
        "document_type": document_type,
        "section_count": len(sections),
        "chunk_count": len(chunks),
        "heading_count": len(headings),
        "section_headings": headings[:20],
        "topic_seeds": top_keywords,
        "pedagogy_signals": dict(pedagogy_signals),
        "page_span": {
            "start": min(page_numbers) if page_numbers else None,
            "end": max(page_numbers) if page_numbers else None,
        },
        "chunking": chunking_metadata or {},
        "study_readiness": {
            "supports_doubt": True,
            "supports_basic_practice": True,
            "needs_topic_prepare_for_learn": True,
        },
    }
    payload_json = json.dumps(payload, sort_keys=True)
    payload["content_hash"] = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    return payload
