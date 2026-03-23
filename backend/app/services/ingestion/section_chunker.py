import re
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings
from app.services.ingestion.ingestion_types import ChunkData, SectionData, token_len


@dataclass
class SectionChunkingResult:
    chunks: list[ChunkData]
    strategy: str
    metadata: dict = field(default_factory=dict)


class SectionChunker:
    def __init__(
        self,
        embedding_model_id: Optional[str] = None,
        embedding_provider_name: Optional[str] = None,
        max_tokens: int = 1600,
        min_tokens: int = 400,
    ) -> None:
        self.embedding_model_id = embedding_model_id or settings.EMBEDDING_MODEL_ID
        self.embedding_provider_name = (
            (embedding_provider_name or settings.EMBEDDING_PROVIDER or "")
            .strip()
            .lower()
        )
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self._allow_tokenizer_download = self.embedding_provider_name not in {
            "openrouter",
            "gemini",
            "mock",
        }

    def chunk(self, *, sections: list[SectionData]) -> SectionChunkingResult:
        chunks = self._merge_small_chunks(
            self._enforce_chunk_token_limit(self._chunk_sections(sections))
        )
        return SectionChunkingResult(
            chunks=chunks,
            strategy="section_markdown",
            metadata={
                "embedding_strategy": "raw",
                "embedding_model_id": self.embedding_model_id,
            },
        )

    def _build_chunk_data(
        self,
        *,
        chunk_index: int,
        text: str,
        section_heading: Optional[str],
        page_start: Optional[int],
        page_end: Optional[int],
        metadata: Optional[dict] = None,
    ) -> ChunkData:
        normalized_metadata = self._with_source_spans(
            text, page_start, page_end, metadata
        )
        resolved_page_start, resolved_page_end = self._page_range_from_spans(
            normalized_metadata.get("source_spans") or [],
            page_start,
            page_end,
        )
        return ChunkData(
            chunk_index=chunk_index,
            text=text,
            section_heading=section_heading,
            page_start=resolved_page_start,
            page_end=resolved_page_end,
            metadata=normalized_metadata,
        )

    def _with_source_spans(
        self,
        text: str,
        page_start: Optional[int],
        page_end: Optional[int],
        metadata: Optional[dict],
    ) -> dict:
        merged = dict(metadata or {})
        merged["source_spans"] = self._normalize_source_spans(
            merged.get("source_spans"),
            len(text),
            page_start,
            page_end,
        )
        return merged

    def _normalize_source_spans(
        self,
        spans: object,
        text_length: int,
        page_start: Optional[int],
        page_end: Optional[int],
    ) -> list[dict]:
        normalized: list[dict] = []
        if isinstance(spans, list):
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
        if text_length <= 0:
            return []
        return [
            {
                "chunk_char_start": 0,
                "chunk_char_end": text_length,
                "page_start": page_start,
                "page_end": page_end,
            }
        ]

    def _source_spans_for_chunk(self, chunk: ChunkData) -> list[dict]:
        metadata = dict(chunk.metadata or {})
        return self._normalize_source_spans(
            metadata.get("source_spans"),
            len(chunk.text or ""),
            chunk.page_start,
            chunk.page_end,
        )

    def _shift_source_spans(self, spans: list[dict], offset: int) -> list[dict]:
        return [
            {
                **span,
                "chunk_char_start": int(span.get("chunk_char_start", 0)) + offset,
                "chunk_char_end": int(span.get("chunk_char_end", 0)) + offset,
            }
            for span in spans
        ]

    def _merge_chunk_metadata(
        self,
        left: ChunkData,
        right: ChunkData,
        separator_len: int,
    ) -> dict:
        merged = {
            key: value
            for key, value in dict(left.metadata or {}).items()
            if key != "source_spans"
        }
        merged.update(
            {
                key: value
                for key, value in dict(right.metadata or {}).items()
                if key != "source_spans"
            }
        )
        merged["source_spans"] = self._source_spans_for_chunk(
            left
        ) + self._shift_source_spans(
            self._source_spans_for_chunk(right),
            len(left.text or "") + separator_len,
        )
        return merged

    def _slice_chunk_metadata(
        self,
        chunk: ChunkData,
        start: int,
        end: int,
    ) -> dict:
        sliced = {
            key: value
            for key, value in dict(chunk.metadata or {}).items()
            if key != "source_spans"
        }
        spans: list[dict] = []
        for span in self._source_spans_for_chunk(chunk):
            span_start = int(span.get("chunk_char_start", 0))
            span_end = int(span.get("chunk_char_end", 0))
            overlap_start = max(start, span_start)
            overlap_end = min(end, span_end)
            if overlap_end <= overlap_start:
                continue
            spans.append(
                {
                    "chunk_char_start": overlap_start - start,
                    "chunk_char_end": overlap_end - start,
                    "page_start": self._coerce_int(span.get("page_start")),
                    "page_end": self._coerce_int(span.get("page_end")),
                }
            )
        if not spans and end > start:
            spans.append(
                {
                    "chunk_char_start": 0,
                    "chunk_char_end": end - start,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                }
            )
        sliced["source_spans"] = spans
        return sliced

    def _coerce_int(self, value: object) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _page_range_from_spans(
        self,
        spans: list[dict],
        fallback_start: Optional[int],
        fallback_end: Optional[int],
    ) -> tuple[Optional[int], Optional[int]]:
        starts = [
            self._coerce_int(span.get("page_start"))
            for span in spans
            if self._coerce_int(span.get("page_start")) is not None
        ]
        ends = [
            self._coerce_int(span.get("page_end"))
            for span in spans
            if self._coerce_int(span.get("page_end")) is not None
        ]
        return (
            min(starts) if starts else fallback_start,
            max(ends) if ends else fallback_end,
        )

    def _chunk_sections(self, sections: list[SectionData]) -> list[ChunkData]:
        chunks: list[ChunkData] = []
        chunk_index = 0
        for section in sections:
            paragraphs = [p.strip() for p in section.text.split("\n\n") if p.strip()]
            if not paragraphs:
                paragraphs = [section.text.strip()] if section.text.strip() else []

            current_parts: list[str] = []
            current_tokens = 0
            for paragraph in paragraphs:
                para_tokens = token_len(paragraph)
                exceeds = current_parts and (
                    current_tokens + para_tokens > self.max_tokens
                )
                if exceeds:
                    chunks.append(
                        self._build_chunk_data(
                            chunk_index=chunk_index,
                            text="\n\n".join(current_parts).strip(),
                            section_heading=section.heading,
                            page_start=section.page_start,
                            page_end=section.page_end,
                            metadata=dict(section.metadata or {}),
                        )
                    )
                    chunk_index += 1
                    current_parts = [paragraph]
                    current_tokens = para_tokens
                    continue

                current_parts.append(paragraph)
                current_tokens += para_tokens

            if current_parts:
                chunks.append(
                    self._build_chunk_data(
                        chunk_index=chunk_index,
                        text="\n\n".join(current_parts).strip(),
                        section_heading=section.heading,
                        page_start=section.page_start,
                        page_end=section.page_end,
                        metadata=dict(section.metadata or {}),
                    )
                )
                chunk_index += 1
        return chunks

    def _merge_small_chunks(self, chunks: list[ChunkData]) -> list[ChunkData]:
        if not chunks:
            return []
        merged: list[ChunkData] = []
        buffer: Optional[ChunkData] = None
        for chunk in chunks:
            chunk_tokens = token_len(chunk.text)
            if buffer is None:
                buffer = self._build_chunk_data(
                    chunk_index=0,
                    text=chunk.text,
                    section_heading=chunk.section_heading,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    metadata=dict(chunk.metadata or {}),
                )
                continue

            buffer_tokens = token_len(buffer.text)
            compatible_heading = buffer.section_heading == chunk.section_heading
            compatible_pages = (
                buffer.page_end is None
                or chunk.page_start is None
                or chunk.page_start <= (buffer.page_end + 1)
            )
            within_capacity = (buffer_tokens + chunk_tokens) <= self.max_tokens
            small_fragment = (
                buffer_tokens < self.min_tokens or chunk_tokens < self.min_tokens
            )
            should_merge = (
                compatible_pages
                and within_capacity
                and (compatible_heading or small_fragment)
            )
            if should_merge:
                separator_len = 2 if buffer.text and chunk.text else 0
                merged_metadata = self._merge_chunk_metadata(
                    buffer,
                    chunk,
                    separator_len,
                )
                buffer.text = (buffer.text + "\n\n" + chunk.text).strip()
                buffer.page_start, buffer.page_end = self._page_range_from_spans(
                    merged_metadata.get("source_spans") or [],
                    buffer.page_start,
                    chunk.page_end,
                )
                buffer.metadata = merged_metadata
                continue

            buffer.chunk_index = len(merged)
            merged.append(buffer)
            buffer = self._build_chunk_data(
                chunk_index=0,
                text=chunk.text,
                section_heading=chunk.section_heading,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                metadata=dict(chunk.metadata or {}),
            )

        if buffer is not None:
            buffer.chunk_index = len(merged)
            merged.append(buffer)
        return merged

    def _enforce_chunk_token_limit(self, chunks: list[ChunkData]) -> list[ChunkData]:
        normalized: list[ChunkData] = []
        for chunk in chunks:
            if token_len(chunk.text) <= self.max_tokens:
                normalized.append(
                    self._build_chunk_data(
                        chunk_index=0,
                        text=chunk.text,
                        section_heading=chunk.section_heading,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        metadata=dict(chunk.metadata or {}),
                    )
                )
                continue
            normalized.extend(self._split_oversized_chunk(chunk))

        for index, chunk in enumerate(normalized):
            chunk.chunk_index = index
        return normalized

    def _split_oversized_chunk(self, chunk: ChunkData) -> list[ChunkData]:
        text = chunk.text or ""
        if not text.strip():
            return []
        spans = self._split_text_spans(text)
        if not spans:
            spans = self._locate_parts(text, self._hard_split_text(text))

        pieces: list[ChunkData] = []
        current_parts: list[tuple[str, int, int]] = []
        current_tokens = 0

        def flush() -> None:
            nonlocal current_parts, current_tokens
            if not current_parts:
                return
            piece_start = current_parts[0][1]
            piece_end = current_parts[-1][2]
            piece_text = text[piece_start:piece_end]
            if piece_text.strip():
                pieces.append(
                    self._build_chunk_data(
                        chunk_index=0,
                        text=piece_text,
                        section_heading=chunk.section_heading,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        metadata=self._slice_chunk_metadata(
                            chunk, piece_start, piece_end
                        ),
                    )
                )
            current_parts = []
            current_tokens = 0

        for span, span_start, span_end in spans:
            span_tokens = token_len(span)
            if span_tokens > self.max_tokens:
                flush()
                hard_offset = 0
                for hard_piece in self._hard_split_text(span):
                    hard_text = hard_piece.strip()
                    if not hard_text:
                        continue
                    local_start = span.find(hard_text, hard_offset)
                    if local_start == -1:
                        local_start = hard_offset
                    local_end = local_start + len(hard_text)
                    hard_offset = local_end
                    pieces.append(
                        self._build_chunk_data(
                            chunk_index=0,
                            text=text[
                                span_start + local_start : span_start + local_end
                            ],
                            section_heading=chunk.section_heading,
                            page_start=chunk.page_start,
                            page_end=chunk.page_end,
                            metadata=self._slice_chunk_metadata(
                                chunk,
                                span_start + local_start,
                                span_start + local_end,
                            ),
                        )
                    )
                continue

            if current_parts and current_tokens + span_tokens > self.max_tokens:
                flush()

            current_parts.append((span, span_start, span_end))
            current_tokens += span_tokens

        flush()
        return pieces

    def _split_text_spans(self, text: str) -> list[tuple[str, int, int]]:
        paragraphs = self._locate_parts(
            text,
            [
                paragraph.strip()
                for paragraph in text.split("\n\n")
                if paragraph.strip()
            ],
        )
        if len(paragraphs) > 1:
            return paragraphs
        sentences = self._split_sentences(text)
        if len(sentences) > 1:
            return sentences
        return paragraphs or sentences

    def _split_sentences(self, text: str) -> list[tuple[str, int, int]]:
        return self._locate_parts(
            text,
            [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()],
        )

    def _locate_parts(self, text: str, parts: list[str]) -> list[tuple[str, int, int]]:
        results: list[tuple[str, int, int]] = []
        offset = 0
        for part in parts:
            stripped = part.strip()
            if not stripped:
                continue
            start = text.find(stripped, offset)
            if start == -1:
                start = offset
            end = start + len(stripped)
            results.append((stripped, start, end))
            offset = end
        return results

    def _hard_split_text(self, text: str) -> list[str]:
        words = [word for word in text.split() if word]
        if not words:
            stripped = text.strip()
            return [stripped] if stripped else []

        pieces: list[str] = []
        current_words: list[str] = []
        for word in words:
            candidate_words = current_words + [word]
            candidate_text = " ".join(candidate_words)
            if current_words and token_len(candidate_text) > self.max_tokens:
                pieces.append(" ".join(current_words))
                current_words = [word]
                continue
            if token_len(candidate_text) > self.max_tokens:
                pieces.extend(self._bisect_oversized_word(word))
                current_words = []
                continue
            current_words = candidate_words
        if current_words:
            pieces.append(" ".join(current_words))
        return [piece.strip() for piece in pieces if piece and piece.strip()]

    def _bisect_oversized_word(self, word: str) -> list[str]:
        pieces: list[str] = []
        remaining = word
        while remaining:
            if token_len(remaining) <= self.max_tokens:
                pieces.append(remaining)
                break
            low = 1
            high = len(remaining)
            best = 1
            while low <= high:
                mid = (low + high) // 2
                candidate = remaining[:mid]
                if token_len(candidate) <= self.max_tokens:
                    best = mid
                    low = mid + 1
                else:
                    high = mid - 1
            piece = remaining[:best].strip()
            if not piece:
                piece = remaining[:1]
                best = 1
            pieces.append(piece)
            remaining = remaining[best:]
        return [piece for piece in pieces if piece]
