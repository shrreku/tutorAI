import hashlib
import json
import re
from collections import Counter
from typing import Any, Optional

STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "into", "your", "have", "will", "are",
    "was", "were", "their", "there", "about", "which", "when", "where", "then", "than", "them",
    "through", "chapter", "section", "page", "pages", "figure", "table", "using", "used", "study",
    "notes", "topic", "topics", "resource", "material", "content", "learn", "practice", "revision",
}


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text or "")]


def _slugify(parts: list[str]) -> str:
    tokens: list[str] = []
    for part in parts:
        tokens.extend(_tokenize(part))
    if not tokens:
        return "general"
    return "-".join(tokens[:8])


def _focus_terms(topic: Optional[str], selected_topics: Optional[list[str]], resource_profile: Optional[dict]) -> list[str]:
    terms: list[str] = []
    if selected_topics:
        for item in selected_topics:
            terms.extend(_tokenize(item))
    if topic:
        terms.extend(_tokenize(topic))
    if not terms and resource_profile:
        terms.extend(_tokenize(" ".join(resource_profile.get("topic_seeds", [])[:4])))
    deduped = list(dict.fromkeys(token for token in terms if token not in STOPWORDS))
    return deduped[:8]


def build_topic_preparation_artifact(
    *,
    mode: str,
    topic: Optional[str],
    selected_topics: Optional[list[str]],
    resource_profile: Optional[dict],
    chunks: list[Any],
) -> dict:
    """Build a deterministic topic-scoped study slice artifact."""
    normalized_mode = (mode or "learn").strip().lower()
    focus_terms = _focus_terms(topic, selected_topics, resource_profile)

    scored_rows: list[tuple[float, Any]] = []
    for chunk in chunks:
        text = getattr(chunk, "text", "") or ""
        heading = getattr(chunk, "section_heading", "") or ""
        text_tokens = Counter(token for token in _tokenize(text) if token not in STOPWORDS)
        heading_tokens = set(token for token in _tokenize(heading) if token not in STOPWORDS)

        overlap = sum(min(2, text_tokens.get(term, 0)) for term in focus_terms)
        heading_boost = sum(2 for term in focus_terms if term in heading_tokens)
        pedagogy = (getattr(chunk, "pedagogy_role", None) or "").lower()
        pedagogy_boost = 0.0
        if normalized_mode == "learn" and pedagogy in {"definition", "example"}:
            pedagogy_boost = 1.5
        elif normalized_mode == "practice" and pedagogy in {"exercise", "example"}:
            pedagogy_boost = 1.5
        elif normalized_mode == "revision" and pedagogy in {"definition", "exercise"}:
            pedagogy_boost = 1.0

        summary_boost = 1.0 if "summary" in text.lower() or "summary" in heading.lower() else 0.0
        score = overlap + heading_boost + pedagogy_boost + summary_boost
        if not focus_terms:
            score += 0.5 if pedagogy else 0.0
        scored_rows.append((score, chunk))

    scored_rows.sort(
        key=lambda item: (
            item[0],
            -int(getattr(item[1], "chunk_index", 0) or 0),
        ),
        reverse=True,
    )
    selected_chunks = [chunk for score, chunk in scored_rows if score > 0][:6]
    if not selected_chunks:
        selected_chunks = [chunk for _, chunk in scored_rows[:4]]

    keyword_counter: Counter[str] = Counter()
    pedagogy_mix: Counter[str] = Counter()
    headings: list[str] = []
    chunk_ids: list[str] = []
    for chunk in selected_chunks:
        text = getattr(chunk, "text", "") or ""
        heading = (getattr(chunk, "section_heading", "") or "").strip()
        if heading and heading not in headings:
            headings.append(heading)
        keyword_counter.update(token for token in _tokenize(text) if token not in STOPWORDS)
        pedagogy = getattr(chunk, "pedagogy_role", None)
        if pedagogy:
            pedagogy_mix[pedagogy] += 1
        chunk_id = getattr(chunk, "id", None)
        if chunk_id is not None:
            chunk_ids.append(str(chunk_id))

    concept_seeds = [token for token, _ in keyword_counter.most_common(10)][:6]
    scope_key = _slugify(selected_topics or ([topic] if topic else focus_terms))
    payload = {
        "artifact_kind": "topic_prepare",
        "artifact_version": "1.0",
        "mode": normalized_mode,
        "topic": topic,
        "selected_topics": selected_topics or [],
        "scope_key": scope_key,
        "focus_terms": focus_terms,
        "selected_chunk_ids": chunk_ids,
        "representative_headings": headings[:8],
        "concept_seeds": concept_seeds,
        "pedagogy_mix": dict(pedagogy_mix),
        "chunk_count_considered": len(chunks),
        "chunk_count_selected": len(selected_chunks),
        "document_type": (resource_profile or {}).get("document_type"),
        "topic_seed_source": (resource_profile or {}).get("topic_seeds", []),
        "notes": [
            "Built from stored chunks and lightweight resource profile.",
            "Intended to improve study-session grounding before full curriculum preparation.",
        ],
    }
    payload_json = json.dumps(payload, sort_keys=True)
    payload["content_hash"] = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    return payload
