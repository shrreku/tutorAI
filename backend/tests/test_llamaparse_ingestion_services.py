import asyncio

from types import SimpleNamespace

from app.services.ingestion.ingestion_types import SectionData, token_len
from app.services.ingestion.docling_adapter import DoclingAdapter
from app.services.ingestion.docling_chunker import DoclingChunker
from app.services.ingestion.llamaparse_adapter import LlamaParseAdapter
from app.services.ingestion.section_chunker import SectionChunker


def test_llamaparse_adapter_extracts_markdown_page_sections():
    adapter = LlamaParseAdapter()

    sections = adapter._extract_sections(
        {
            "markdown": {
                "pages": [
                    {"page_number": 1, "markdown": "# Intro\nHeat transfer basics."},
                    {
                        "page_number": 2,
                        "markdown": "## Conduction\nConduction details.",
                    },
                ]
            }
        }
    )

    assert len(sections) == 2
    assert sections[0].heading == "Intro"
    assert sections[0].page_start == 1
    assert sections[1].heading == "Conduction"
    assert sections[1].page_start == 2


def test_llamaparse_adapter_builds_page_summaries():
    adapter = LlamaParseAdapter()

    pages = adapter._extract_page_summaries(
        {
            "markdown": {
                "pages": [
                    {"page_number": 1, "markdown": "intro"},
                    {"page_number": 2, "markdown": "content"},
                ]
            },
            "text": {
                "pages": [
                    {"page_number": 1, "text": "intro text"},
                    {"page_number": 2, "text": "content text"},
                ]
            },
            "items": {
                "pages": [
                    {"page_number": 2, "items": [{"type": "table"}, {"type": "figure"}]}
                ]
            },
        }
    )

    assert pages == [
        {"page_number": 1, "has_markdown": True, "has_text": True},
        {"page_number": 2, "has_markdown": True, "has_text": True, "item_count": 2},
    ]


def test_section_chunker_enforces_parent_chunk_token_budget():
    chunker = SectionChunker(max_tokens=30, min_tokens=5)
    sections = [
        SectionData(
            heading="Intro",
            page_start=1,
            page_end=1,
            text=(
                "Sentence one has enough words to create pressure on the token budget. "
                "Sentence two keeps going so the chunker must split before returning chunks. "
                "Sentence three forces at least one more split boundary."
            ),
            metadata={"source": "llamaparse_markdown"},
        )
    ]

    result = chunker.chunk(sections=sections)

    assert result.strategy == "section_markdown"
    assert len(result.chunks) >= 2
    assert all(token_len(chunk.text) <= 30 for chunk in result.chunks)
    assert result.metadata["embedding_strategy"] == "raw"


def test_section_chunker_merges_small_adjacent_chunks():
    chunker = SectionChunker(max_tokens=1600, min_tokens=400)
    merged = chunker._merge_small_chunks(
        [
            type(
                "Chunk",
                (),
                {
                    "chunk_index": 0,
                    "text": "A " * 180,
                    "section_heading": "Intro",
                    "page_start": 1,
                    "page_end": 1,
                    "metadata": {"a": 1},
                },
            )(),
            type(
                "Chunk",
                (),
                {
                    "chunk_index": 1,
                    "text": "B " * 180,
                    "section_heading": "Intro",
                    "page_start": 1,
                    "page_end": 1,
                    "metadata": {"b": 2},
                },
            )(),
        ]
    )

    assert len(merged) == 1
    assert merged[0].chunk_index == 0
    assert "A " in merged[0].text
    assert "B " in merged[0].text


def test_docling_adapter_delegates_to_llamaparse_when_api_key_is_set(monkeypatch):
    adapter = DoclingAdapter()

    monkeypatch.setattr(
        "app.services.ingestion.docling_adapter.settings",
        SimpleNamespace(
            LLAMAPARSE_API_KEY="test-key",
            INGESTION_DOCLING_PROFILE="balanced",
        ),
    )

    async def _fake_llamaparse_convert(self, source: str):
        return SimpleNamespace(
            source=source,
            source_type="file",
            status="SUCCESS",
            sections=[
                SectionData(
                    heading="Intro",
                    page_start=1,
                    page_end=1,
                    text="Hello from remote parsing.",
                )
            ],
            warnings=["remote warning"],
            errors=[],
            metadata={"llamaparse": {"job_id": "job-123"}},
        )

    monkeypatch.setattr(
        "app.services.ingestion.llamaparse_adapter.LlamaParseAdapter.convert",
        _fake_llamaparse_convert,
    )
    monkeypatch.setattr(
        "app.services.ingestion.docling_adapter.DoclingAdapter._get_converter",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Docling converter should not be initialized")
        ),
    )

    result = asyncio.run(adapter.convert("https://example.com/resource.pdf"))

    assert result.docling_document is None
    assert result.source_type == "file"
    assert result.sections[0].heading == "Intro"
    assert result.metadata["docling"]["delegated_to"] == "llamaparse"
    assert result.metadata["llamaparse"]["job_id"] == "job-123"


def test_docling_chunker_skips_tokenizer_download_for_remote_embeddings(monkeypatch):
    chunker = DoclingChunker(
        embedding_model_id="google/gemini-embedding-001",
        embedding_provider_name="openrouter",
    )

    monkeypatch.setattr(
        "transformers.AutoTokenizer.from_pretrained",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Tokenizer download should not be attempted")
        ),
    )

    assert chunker._build_docling_tokenizer() is None
