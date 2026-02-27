"""
Semantic Deduplication Utility - TICKET-054

Embedding-based deduplication for learning objectives, topics, concepts,
prerequisites, and terminology. Used by ontology extractor merge step.
"""
import logging
from typing import Callable, Optional, Awaitable

import numpy as np

logger = logging.getLogger(__name__)


def quick_string_dedup(items: list[dict], text_key: str) -> list[dict]:
    """Fast exact/substring dedup before expensive embedding step."""
    if len(items) <= 1:
        return items

    seen: list[str] = []
    result: list[dict] = []
    for item in items:
        text = item.get(text_key, "").lower().strip()
        if not text:
            result.append(item)
            continue
        is_dup = False
        for s in seen:
            if text in s or s in text:
                is_dup = True
                break
        if not is_dup:
            seen.append(text)
            result.append(item)
    return result


async def semantic_dedup(
    items: list[dict],
    text_key: str,
    embed_fn: Callable[[list[str]], Awaitable[list[list[float]]]],
    similarity_threshold: float = 0.85,
    merge_strategy: str = "keep_longer",
    score_key: Optional[str] = None,
) -> list[dict]:
    """
    Deduplicate a list of dicts by embedding similarity on text_key.

    Args:
        items: List of dicts to deduplicate.
        text_key: Key in each dict containing the text to compare.
        embed_fn: Async function that embeds a list of strings -> list of vectors.
        similarity_threshold: Cosine similarity above which items are duplicates.
        merge_strategy: "keep_longer" | "keep_first" | "keep_higher_score"
        score_key: Optional key for score-based merge strategy.

    Returns:
        Deduplicated list.
    """
    if len(items) <= 1:
        return items

    # Quick string dedup first (fast path)
    items = quick_string_dedup(items, text_key)
    if len(items) <= 1:
        return items

    texts = [item.get(text_key, "") for item in items]
    embeddings_raw = await embed_fn(texts)
    embeddings = np.array(embeddings_raw, dtype=np.float32)

    # Normalize for cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = embeddings / norms

    # Greedy dedup
    keep_indices: list[int] = [0]
    for i in range(1, len(items)):
        is_dup = False
        for j in keep_indices:
            sim = float(np.dot(embeddings[i], embeddings[j]))
            if sim > similarity_threshold:
                is_dup = True
                # Decide which to keep based on strategy
                if merge_strategy == "keep_longer":
                    if len(texts[i]) > len(texts[j]):
                        keep_indices[keep_indices.index(j)] = i
                elif merge_strategy == "keep_higher_score" and score_key:
                    if items[i].get(score_key, 0) > items[j].get(score_key, 0):
                        keep_indices[keep_indices.index(j)] = i
                # "keep_first" does nothing (keeps existing)
                break
        if not is_dup:
            keep_indices.append(i)

    deduped = [items[i] for i in keep_indices]
    if len(deduped) < len(items):
        logger.info(
            f"[SEMANTIC_DEDUP] Deduped {len(items)} -> {len(deduped)} items "
            f"(key={text_key}, threshold={similarity_threshold})"
        )
    return deduped
