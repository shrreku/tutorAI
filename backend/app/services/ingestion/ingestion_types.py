import re
from dataclasses import dataclass, field
from typing import Optional


def token_len(text: str) -> int:
    """Estimate token count for text."""
    try:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text or ""))
    except ImportError:
        # Fallback: rough estimate (1 token ~= 0.75 words)
        return int(len((text or "").split()) * 1.33)


@dataclass
class SectionData:
    """Normalized section extracted during conversion."""

    heading: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ChunkData:
    """A chunk of text ready for embedding and enrichment."""

    chunk_index: int
    text: str
    section_heading: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    metadata: dict = field(default_factory=dict)


def split_markdown_sections(markdown_text: str) -> list[SectionData]:
    """Split markdown into coarse sections by heading boundaries."""
    text = (markdown_text or "").strip()
    if not text:
        return []

    heading_pattern = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
    matches = list(heading_pattern.finditer(text))
    if not matches:
        return [
            SectionData(
                heading=None,
                page_start=None,
                page_end=None,
                text=text,
                metadata={"source": "docling_markdown"},
            )
        ]

    sections: list[SectionData] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        heading = match.group(1).strip()
        sections.append(
            SectionData(
                heading=heading,
                page_start=None,
                page_end=None,
                text=body,
                metadata={"source": "docling_markdown"},
            )
        )

    return sections
