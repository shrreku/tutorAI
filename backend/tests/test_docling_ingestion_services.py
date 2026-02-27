import asyncio
from types import SimpleNamespace

from app.services.ingestion.docling_adapter import DoclingAdapter
from app.services.ingestion.docling_chunker import DoclingChunker
from app.services.ingestion.docling_config import (
    _apply_base_options,
    _apply_override_options,
    _apply_profile_options,
)
from app.services.ingestion.ingestion_types import SectionData


class _FakeDoc:
    def export_to_markdown(self) -> str:
        return "# Intro\nHeat transfer basics.\n\n## Conduction\nConduction details."


class _FakeConversion:
    def __init__(self):
        self.status = "SUCCESS"
        self.document = _FakeDoc()
        self.warnings = ["partial layout"]
        self.errors = []


class _FakeConverter:
    def convert(self, source, raises_on_error=False):
        return _FakeConversion()


def test_docling_adapter_normalizes_result(monkeypatch):
    adapter = DoclingAdapter()
    monkeypatch.setattr(adapter, "_get_converter", lambda: _FakeConverter())

    result = asyncio.run(adapter.convert("https://example.com/test.pdf"))

    assert result.status == "SUCCESS"
    assert result.source_type == "url"
    assert len(result.sections) == 2
    assert result.sections[0].heading == "Intro"
    assert result.metadata["sections_count"] == 2


def test_docling_chunker_fallback_chunking():
    chunker = DoclingChunker(max_tokens=30, min_tokens=5)
    sections = [
        SectionData(
            heading="Intro",
            page_start=1,
            page_end=1,
            text=(
                "Paragraph one with enough content to form a chunk.\n\n"
                "Paragraph two extends the section and should remain deterministic."
            ),
        )
    ]

    result = chunker.chunk(docling_document=None, sections=sections)

    assert result.strategy == "section_fallback"
    assert len(result.chunks) >= 1
    assert result.chunks[0].chunk_index == 0
    assert result.metadata["embedding_strategy"] == "raw"


def test_docling_profile_and_override_behavior(monkeypatch):
    from app.config import settings

    pipeline_options = SimpleNamespace(
        enable_remote_services=True,
        allow_external_plugins=True,
        document_timeout=None,
        artifacts_path=None,
        accelerator_options=SimpleNamespace(device="auto", num_threads=1),
        ocr_options=SimpleNamespace(lang=[], kind="ocr_auto"),
        table_structure_options=SimpleNamespace(mode="accurate", do_cell_matching=True),
        do_ocr=True,
        do_formula_enrichment=False,
        do_code_enrichment=False,
        do_picture_classification=False,
        do_picture_description=False,
        do_chart_extraction=False,
        generate_picture_images=False,
        images_scale=1.0,
    )

    monkeypatch.setattr(settings, "INGESTION_DOCLING_PROFILE", "high_fidelity")
    monkeypatch.setattr(settings, "INGESTION_DOCLING_TIMEOUT_S", 90)
    monkeypatch.setattr(settings, "INGESTION_DOCLING_DEVICE", "cpu")
    monkeypatch.setattr(settings, "INGESTION_DOCLING_NUM_THREADS", 2)
    monkeypatch.setattr(settings, "INGESTION_DOCLING_ARTIFACTS_PATH", None)
    monkeypatch.setattr(settings, "INGESTION_DOCLING_OCR_LANGS", "eng,deu")
    monkeypatch.setattr(settings, "INGESTION_DOCLING_OCR_ENGINE", "rapidocr")

    monkeypatch.setattr(settings, "INGESTION_DOCLING_TABLE_MODE", "accurate")
    monkeypatch.setattr(settings, "INGESTION_DOCLING_TABLE_CELL_MATCHING", True)
    monkeypatch.setattr(settings, "INGESTION_DOCLING_FORMULA_ENRICHMENT", None)
    monkeypatch.setattr(settings, "INGESTION_DOCLING_CODE_ENRICHMENT", None)
    monkeypatch.setattr(settings, "INGESTION_DOCLING_PICTURE_IMAGES", None)
    monkeypatch.setattr(settings, "INGESTION_DOCLING_PICTURE_CLASSIFICATION", None)
    monkeypatch.setattr(settings, "INGESTION_DOCLING_PICTURE_DESCRIPTION", None)
    monkeypatch.setattr(settings, "INGESTION_DOCLING_CHART_EXTRACTION", None)

    _apply_base_options(pipeline_options)
    _apply_profile_options(pipeline_options)
    _apply_override_options(pipeline_options)

    assert pipeline_options.enable_remote_services is False
    assert pipeline_options.allow_external_plugins is False
    assert pipeline_options.do_formula_enrichment is True
    assert pipeline_options.do_picture_description is True
    assert pipeline_options.generate_picture_images is True
    assert pipeline_options.images_scale >= 2.0
    assert pipeline_options.ocr_options.lang == ["eng", "deu"]
    assert pipeline_options.ocr_options.kind == "rapidocr"
