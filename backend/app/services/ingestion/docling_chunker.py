import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.services.ingestion.ingestion_types import ChunkData, SectionData, token_len

logger = logging.getLogger(__name__)


@dataclass
class DoclingChunkingResult:
    chunks: list[ChunkData]
    strategy: str
    metadata: dict = field(default_factory=dict)


class DoclingChunker:
    """Chunking service that prefers Docling HybridChunker with deterministic fallback."""

    def __init__(
        self,
        embedding_model_id: Optional[str] = None,
        use_contextualized_text: bool = True,
        max_tokens: int = 1200,
        min_tokens: int = 200,
    ) -> None:
        self.embedding_model_id = embedding_model_id or settings.EMBEDDING_MODEL_ID
        self.use_contextualized_text = use_contextualized_text
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens

    def chunk(
        self,
        *,
        docling_document: Any,
        sections: list[SectionData],
    ) -> DoclingChunkingResult:
        if docling_document is not None:
            try:
                chunks = self._chunk_with_docling(docling_document)
                if chunks:
                    return DoclingChunkingResult(
                        chunks=chunks,
                        strategy="docling_hybrid",
                        metadata={
                            "embedding_strategy": (
                                "contextualized" if self.use_contextualized_text else "raw"
                            ),
                            "embedding_model_id": self.embedding_model_id,
                        },
                    )
            except Exception as exc:
                logger.warning("Docling HybridChunker failed; falling back to section chunking: %s", exc)

        fallback_chunks = self._chunk_sections_fallback(sections)
        return DoclingChunkingResult(
            chunks=fallback_chunks,
            strategy="section_fallback",
            metadata={
                "embedding_strategy": "raw",
                "embedding_model_id": self.embedding_model_id,
            },
        )

    # Minimum character threshold: chunks smaller than this are likely
    # noise (e.g., lone chapter headers) and will be filtered out.
    MIN_CHUNK_CHARS = 50

    def _chunk_with_docling(self, docling_document: Any) -> list[ChunkData]:
        from docling.chunking import HybridChunker

        tokenizer = self._build_docling_tokenizer()
        if tokenizer is not None:
            chunker = HybridChunker(tokenizer=tokenizer, merge_peers=True)
        else:
            chunker = HybridChunker(merge_peers=True)

        chunk_iter = chunker.chunk(dl_doc=docling_document)
        chunks: list[ChunkData] = []
        real_index = 0

        for raw_chunk in chunk_iter:
            text = self._serialize_chunk(chunker=chunker, chunk=raw_chunk)
            if not text.strip():
                continue

            # Skip trivially small chunks (chapter header artifacts, etc.)
            if len(text.strip()) < self.MIN_CHUNK_CHARS:
                logger.debug("Skipping trivially small chunk (%d chars): %s", len(text.strip()), text[:60])
                continue

            heading = self._extract_heading(raw_chunk)
            page_start, page_end = self._extract_page_range(raw_chunk)
            metadata = self._extract_chunk_metadata(raw_chunk)

            chunks.append(
                ChunkData(
                    chunk_index=real_index,
                    text=text,
                    section_heading=heading,
                    page_start=page_start,
                    page_end=page_end,
                    metadata=metadata,
                )
            )
            real_index += 1

        return chunks

    def _serialize_chunk(self, *, chunker: Any, chunk: Any) -> str:
        if self.use_contextualized_text:
            contextualize = getattr(chunker, "contextualize", None)
            if callable(contextualize):
                serialized = contextualize(chunk=chunk)
                if isinstance(serialized, str) and serialized.strip():
                    return serialized

        text = getattr(chunk, "text", "")
        return text if isinstance(text, str) else str(text)

    def _build_docling_tokenizer(self) -> Any:
        model_id = (self.embedding_model_id or "").strip()
        if not model_id:
            return None

        try:
            if model_id.startswith("text-") or model_id.startswith("gpt-"):
                import tiktoken
                from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer

                encoding = tiktoken.encoding_for_model("gpt-4o")
                return OpenAITokenizer(tokenizer=encoding, max_tokens=8192)

            from transformers import AutoTokenizer
            from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

            hf_tokenizer = AutoTokenizer.from_pretrained(model_id)
            return HuggingFaceTokenizer(tokenizer=hf_tokenizer)
        except Exception as exc:
            logger.warning("Docling tokenizer alignment unavailable for %s: %s", model_id, exc)
            return None

    def _chunk_sections_fallback(self, sections: list[SectionData]) -> list[ChunkData]:
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
                exceeds = current_parts and (current_tokens + para_tokens > self.max_tokens)
                if exceeds:
                    text = "\n\n".join(current_parts).strip()
                    if text:
                        chunks.append(
                            ChunkData(
                                chunk_index=chunk_index,
                                text=text,
                                section_heading=section.heading,
                                page_start=section.page_start,
                                page_end=section.page_end,
                                metadata={"source": "fallback"},
                            )
                        )
                        chunk_index += 1
                    current_parts = [paragraph]
                    current_tokens = para_tokens
                else:
                    current_parts.append(paragraph)
                    current_tokens += para_tokens

            if current_parts:
                text = "\n\n".join(current_parts).strip()
                if text:
                    if chunks and token_len(text) < self.min_tokens:
                        prev = chunks[-1]
                        merged = f"{prev.text}\n\n{text}".strip()
                        if token_len(merged) <= int(self.max_tokens * 1.2):
                            prev.text = merged
                            prev.page_end = section.page_end
                            continue

                    chunks.append(
                        ChunkData(
                            chunk_index=chunk_index,
                            text=text,
                            section_heading=section.heading,
                            page_start=section.page_start,
                            page_end=section.page_end,
                            metadata={"source": "fallback"},
                        )
                    )
                    chunk_index += 1

        return chunks

    def _extract_heading(self, raw_chunk: Any) -> Optional[str]:
        """Extract section heading from a Docling chunk.

        Docling's DocMeta stores headings in ``meta.headings`` as a list
        of strings (the hierarchy of section headings for that chunk).
        We take the *last* element as the most specific heading.
        """
        meta = getattr(raw_chunk, "meta", None)

        # Docling DocMeta — meta.headings is a list[str]
        if meta is not None:
            headings = getattr(meta, "headings", None)
            if isinstance(headings, list) and headings:
                # Take the most specific (deepest) heading
                heading = headings[-1]
                if isinstance(heading, str) and heading.strip():
                    return heading.strip()

        # Fallback: direct attributes
        for attr in ("heading", "section_heading", "title"):
            value = getattr(raw_chunk, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()

        # Fallback: dict-style meta
        if isinstance(meta, dict):
            heading = meta.get("heading") or meta.get("section_heading")
            if isinstance(heading, str) and heading.strip():
                return heading.strip()

        return None

    def _extract_page_range(self, raw_chunk: Any) -> tuple[Optional[int], Optional[int]]:
        """Extract page range from a Docling chunk.

        Docling's DocMeta stores page provenance in
        ``meta.doc_items[*].prov[*].page_no``.
        We collect all page numbers and return (min, max).
        """
        meta = getattr(raw_chunk, "meta", None)
        pages: list[int] = []

        # Docling DocMeta — iterate doc_items → prov → page_no
        if meta is not None:
            doc_items = getattr(meta, "doc_items", None)
            if isinstance(doc_items, list):
                for item in doc_items:
                    prov = getattr(item, "prov", None)
                    if isinstance(prov, list):
                        for p in prov:
                            page_no = getattr(p, "page_no", None)
                            if isinstance(page_no, int):
                                pages.append(page_no)

        if pages:
            return min(pages), max(pages)

        # Fallback: dict-style meta
        if isinstance(meta, dict):
            ps = meta.get("page_start")
            pe = meta.get("page_end")
            if isinstance(ps, int) or isinstance(pe, int):
                return (ps if isinstance(ps, int) else None), (pe if isinstance(pe, int) else None)

        page = getattr(raw_chunk, "page", None)
        if isinstance(page, int):
            return page, page

        return None, None

    def _extract_chunk_metadata(self, raw_chunk: Any) -> dict:
        from app.services.ingestion.docling_adapter import DoclingAdapter

        metadata: dict = {"source": "docling_hybrid"}

        meta = getattr(raw_chunk, "meta", None)

        # Docling DocMeta — has model_dump()
        if meta is not None and hasattr(meta, "model_dump"):
            try:
                md = meta.model_dump()
                metadata.update(DoclingAdapter._make_json_safe(md))
            except Exception:
                pass
        elif isinstance(meta, dict):
            metadata.update(DoclingAdapter._make_json_safe(meta))

        return metadata
