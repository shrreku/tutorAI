"""Sub-chunker: splits parent chunks into ~512-token retrieval-optimized segments.

Maintains sentence boundary integrity and tracks character offsets
back to the parent chunk for citation precision.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.ingestion.ingestion_types import ChunkData, token_len

logger = logging.getLogger(__name__)

# Sentence-ending pattern: period, !, ? followed by whitespace or end
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class SubChunkData:
    """A sub-chunk with offset tracking back to its parent."""

    parent_chunk_index: int
    sub_index: int
    text: str
    char_start: int  # offset in parent chunk text
    char_end: int  # offset in parent chunk text
    page_start: Optional[int] = None
    page_end: Optional[int] = None


@dataclass
class SubChunkingResult:
    sub_chunks: list[SubChunkData]
    metadata: dict = field(default_factory=dict)


class SubChunker:
    """Splits parent chunks into ~512-token sub-chunks for retrieval.

    Strategy:
    - Split parent text on sentence boundaries
    - Accumulate sentences until target token count (~512)
    - Optional overlap (default 64 tokens) for context continuity
    - Track char_start/char_end offsets into parent
    """

    def __init__(
        self,
        target_tokens: int = 512,
        min_tokens: int = 128,
        overlap_tokens: int = 64,
        max_tokens: int = 496,
    ) -> None:
        self.target_tokens = target_tokens
        self.min_tokens = min_tokens
        self.overlap_tokens = overlap_tokens
        self.max_tokens = max_tokens

    def _coerce_int(self, value: object) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _source_spans(self, chunk: ChunkData) -> list[dict]:
        metadata = dict(chunk.metadata or {})
        spans = metadata.get("source_spans")
        if isinstance(spans, list):
            normalized: list[dict] = []
            text_length = len(chunk.text or "")
            for span in spans:
                if not isinstance(span, dict):
                    continue
                span_start = self._coerce_int(span.get("chunk_char_start"))
                span_end = self._coerce_int(span.get("chunk_char_end"))
                if span_start is None:
                    span_start = 0
                if span_end is None:
                    span_end = text_length
                span_start = max(0, min(span_start, text_length))
                span_end = max(span_start, min(span_end, text_length))
                if span_end <= span_start:
                    continue
                normalized.append(
                    {
                        "chunk_char_start": span_start,
                        "chunk_char_end": span_end,
                        "page_start": self._coerce_int(span.get("page_start")),
                        "page_end": self._coerce_int(span.get("page_end")),
                    }
                )
            if normalized:
                return normalized
        if not (chunk.text or ""):
            return []
        return [
            {
                "chunk_char_start": 0,
                "chunk_char_end": len(chunk.text or ""),
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
            }
        ]

    def _derive_page_range(
        self,
        chunk: ChunkData,
        char_start: int,
        char_end: int,
    ) -> tuple[Optional[int], Optional[int]]:
        starts: list[int] = []
        ends: list[int] = []
        for span in self._source_spans(chunk):
            span_start = int(span.get("chunk_char_start", 0))
            span_end = int(span.get("chunk_char_end", 0))
            overlap_start = max(char_start, span_start)
            overlap_end = min(char_end, span_end)
            if overlap_end <= overlap_start:
                continue
            page_start = self._coerce_int(span.get("page_start"))
            page_end = self._coerce_int(span.get("page_end"))
            if page_start is not None:
                starts.append(page_start)
            if page_end is not None:
                ends.append(page_end)
        return (
            min(starts) if starts else chunk.page_start,
            max(ends) if ends else chunk.page_end,
        )

    def sub_chunk(self, chunks: list[ChunkData]) -> SubChunkingResult:
        """Split all parent chunks into sub-chunks.

        Returns SubChunkingResult with all sub-chunks and metadata.
        """
        all_sub_chunks: list[SubChunkData] = []
        parent_count = 0
        skipped = 0

        for chunk in chunks:
            parent_tokens = token_len(chunk.text)

            # If parent is already small enough, create a single sub-chunk
            if parent_tokens <= self.max_tokens:
                page_start, page_end = self._derive_page_range(
                    chunk,
                    0,
                    len(chunk.text),
                )
                all_sub_chunks.append(
                    SubChunkData(
                        parent_chunk_index=chunk.chunk_index,
                        sub_index=0,
                        text=chunk.text,
                        char_start=0,
                        char_end=len(chunk.text),
                        page_start=page_start,
                        page_end=page_end,
                    )
                )
                parent_count += 1
                continue

            # Split into sub-chunks
            subs = self._split_chunk(chunk)
            if not subs:
                skipped += 1
                continue

            all_sub_chunks.extend(subs)
            parent_count += 1

        logger.info(
            "[SUB-CHUNKER] %d parent chunks → %d sub-chunks (%.1f avg), %d skipped",
            parent_count,
            len(all_sub_chunks),
            len(all_sub_chunks) / max(1, parent_count),
            skipped,
        )

        return SubChunkingResult(
            sub_chunks=all_sub_chunks,
            metadata={
                "parent_count": parent_count,
                "sub_chunk_count": len(all_sub_chunks),
                "target_tokens": self.target_tokens,
                "max_tokens": self.max_tokens,
                "overlap_tokens": self.overlap_tokens,
                "skipped": skipped,
            },
        )

    def _split_chunk(self, chunk: ChunkData) -> list[SubChunkData]:
        """Split a single parent chunk into sub-chunks on sentence boundaries."""
        text = chunk.text
        sentences = self._normalize_spans(text, self._split_sentences(text))
        if not sentences:
            return []

        sub_chunks: list[SubChunkData] = []
        sub_index = 0
        current_sentences: list[
            tuple[str, int, int]
        ] = []  # (text, char_start, char_end)
        current_tokens = 0

        for sent_text, sent_start, sent_end in sentences:
            sent_tokens = token_len(sent_text)

            # If adding this sentence exceeds target, flush current buffer
            if current_sentences and (
                current_tokens + sent_tokens > self.target_tokens
            ):
                sub = self._flush_buffer(
                    chunk,
                    current_sentences,
                    sub_index,
                )
                sub_chunks.append(sub)
                sub_index += 1

                # Compute overlap: keep last N tokens worth of sentences
                current_sentences, current_tokens = self._compute_overlap(
                    current_sentences,
                )
                while (
                    current_sentences and current_tokens + sent_tokens > self.max_tokens
                ):
                    removed = current_sentences.pop(0)
                    current_tokens -= token_len(removed[0])

            current_sentences.append((sent_text, sent_start, sent_end))
            current_tokens += sent_tokens

        # Flush remaining
        if current_sentences:
            # If remaining is too small, merge with previous
            if sub_chunks and current_tokens < self.min_tokens:
                prev = sub_chunks[-1]
                merged_start = prev.char_start
                merged_end = current_sentences[-1][2]
                merged_text = text[merged_start:merged_end]
                if token_len(merged_text) <= self.max_tokens:
                    page_start, page_end = self._derive_page_range(
                        chunk,
                        merged_start,
                        merged_end,
                    )
                    sub_chunks[-1] = SubChunkData(
                        parent_chunk_index=chunk.chunk_index,
                        sub_index=prev.sub_index,
                        text=merged_text,
                        char_start=merged_start,
                        char_end=merged_end,
                        page_start=page_start,
                        page_end=page_end,
                    )
                else:
                    sub = self._flush_buffer(chunk, current_sentences, sub_index)
                    sub_chunks.append(sub)
            else:
                sub = self._flush_buffer(chunk, current_sentences, sub_index)
                sub_chunks.append(sub)

        return sub_chunks

    def _normalize_spans(
        self,
        text: str,
        spans: list[tuple[str, int, int]],
    ) -> list[tuple[str, int, int]]:
        normalized: list[tuple[str, int, int]] = []
        for span_text, span_start, span_end in spans:
            if token_len(span_text) <= self.max_tokens:
                normalized.append((span_text, span_start, span_end))
                continue
            normalized.extend(self._split_oversized_span(text, span_start, span_end))
        return normalized

    def _split_oversized_span(
        self,
        source_text: str,
        start: int,
        end: int,
    ) -> list[tuple[str, int, int]]:
        fragment_text = source_text[start:end]
        if not fragment_text.strip():
            return []

        pieces: list[tuple[str, int, int]] = []
        current_start: Optional[int] = None
        current_end: Optional[int] = None

        for match in re.finditer(r"\S+", fragment_text):
            word_start = start + match.start()
            word_end = start + match.end()
            word_text = source_text[word_start:word_end]
            if token_len(word_text) > self.max_tokens:
                if current_start is not None and current_end is not None:
                    pieces.append(
                        (
                            source_text[current_start:current_end],
                            current_start,
                            current_end,
                        )
                    )
                    current_start = None
                    current_end = None
                pieces.extend(self._hard_split_text(source_text, word_start, word_end))
                continue
            if current_start is None:
                current_start = word_start
                current_end = word_end
                continue

            candidate_end = word_end
            candidate_text = source_text[current_start:candidate_end]
            if token_len(candidate_text) > self.max_tokens:
                pieces.append(
                    (
                        source_text[current_start:current_end],
                        current_start,
                        current_end,
                    )
                )
                current_start = word_start
                current_end = word_end
            else:
                current_end = candidate_end

        if current_start is not None and current_end is not None:
            pieces.append(
                (
                    source_text[current_start:current_end],
                    current_start,
                    current_end,
                )
            )

        if not pieces:
            stripped = fragment_text.strip()
            if stripped:
                stripped_start = source_text.find(stripped, start, end)
                if stripped_start == -1:
                    stripped_start = start
                stripped_end = stripped_start + len(stripped)
                pieces.extend(
                    self._hard_split_text(source_text, stripped_start, stripped_end)
                )
        return pieces

    def _hard_split_text(
        self,
        source_text: str,
        start: int,
        end: int,
    ) -> list[tuple[str, int, int]]:
        pieces: list[tuple[str, int, int]] = []
        cursor = start
        while cursor < end:
            next_end = min(end, cursor + max(1, end - cursor))
            if token_len(source_text[cursor:next_end]) <= self.max_tokens:
                pieces.append((source_text[cursor:next_end], cursor, next_end))
                break

            low = cursor + 1
            high = next_end
            best_end = low
            while low <= high:
                mid = (low + high) // 2
                candidate = source_text[cursor:mid]
                if token_len(candidate) <= self.max_tokens:
                    best_end = mid
                    low = mid + 1
                else:
                    high = mid - 1

            pieces.append((source_text[cursor:best_end], cursor, best_end))
            cursor = best_end
        return pieces

    def _split_sentences(self, text: str) -> list[tuple[str, int, int]]:
        """Split text into sentences, tracking char offsets.

        Returns list of (sentence_text, char_start, char_end).
        """
        results: list[tuple[str, int, int]] = []
        parts = _SENTENCE_END.split(text)
        offset = 0

        for part in parts:
            stripped = part.strip()
            if not stripped:
                offset += len(part)
                # Account for the whitespace that was split on
                while offset < len(text) and text[offset : offset + 1] in (
                    " ",
                    "\n",
                    "\t",
                    "\r",
                ):
                    offset += 1
                continue

            # Find actual position in original text
            start = text.find(stripped, offset)
            if start == -1:
                start = offset
            end = start + len(stripped)
            results.append((stripped, start, end))
            offset = end
            # Skip past whitespace
            while offset < len(text) and text[offset : offset + 1] in (
                " ",
                "\n",
                "\t",
                "\r",
            ):
                offset += 1

        return results

    def _flush_buffer(
        self,
        chunk: ChunkData,
        sentences: list[tuple[str, int, int]],
        sub_index: int,
    ) -> SubChunkData:
        """Create a SubChunkData from accumulated sentences."""
        char_start = sentences[0][1]
        char_end = sentences[-1][2]
        text = chunk.text[char_start:char_end]
        page_start, page_end = self._derive_page_range(chunk, char_start, char_end)

        return SubChunkData(
            parent_chunk_index=chunk.chunk_index,
            sub_index=sub_index,
            text=text,
            char_start=char_start,
            char_end=char_end,
            page_start=page_start,
            page_end=page_end,
        )

    def _compute_overlap(
        self,
        sentences: list[tuple[str, int, int]],
    ) -> tuple[list[tuple[str, int, int]], int]:
        """Keep last N tokens of overlap from previous buffer.

        Returns (overlap_sentences, overlap_token_count).
        """
        if self.overlap_tokens <= 0:
            return [], 0

        overlap: list[tuple[str, int, int]] = []
        overlap_tokens = 0

        for sent in reversed(sentences):
            sent_tokens = token_len(sent[0])
            if overlap_tokens + sent_tokens > self.overlap_tokens:
                break
            overlap.insert(0, sent)
            overlap_tokens += sent_tokens

        return overlap, overlap_tokens
