import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def build_docling_converter():
    """Create a DocumentConverter configured with deterministic Docling options."""
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except (
        ImportError
    ) as exc:  # pragma: no cover - exercised only when dependency missing
        raise RuntimeError(
            "Docling is not installed. Add 'docling' to backend dependencies to use ingestion."
        ) from exc

    pipeline_options = PdfPipelineOptions()
    _apply_base_options(pipeline_options)
    _apply_profile_options(pipeline_options)
    _apply_override_options(pipeline_options)

    logger.info(
        "Docling configured (profile=%s, table_mode=%s, ocr=%s)",
        settings.INGESTION_DOCLING_PROFILE,
        settings.INGESTION_DOCLING_TABLE_MODE,
        getattr(pipeline_options, "do_ocr", True),
    )

    # Build format options for all supported input formats.
    # PDF gets the full pipeline_options; other formats use Docling defaults.
    format_options: dict = {
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
    }

    # Register additional formats when the installed Docling version supports them.
    _optional_formats = {
        "DOCX": "DoclingParseDocumentFormatOption",
        "PPTX": "DoclingParseDocumentFormatOption",
        "HTML": "DoclingParseDocumentFormatOption",
        "MD": "DoclingParseDocumentFormatOption",
        "ASCIIDOC": "DoclingParseDocumentFormatOption",
        "CSV": "DoclingParseDocumentFormatOption",
    }
    for fmt_name in _optional_formats:
        fmt_enum = getattr(InputFormat, fmt_name, None)
        if fmt_enum is not None:
            format_options[fmt_enum] = fmt_enum  # Docling auto-resolves default option
            logger.debug("Registered Docling format: %s", fmt_name)

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        },
        allowed_formats=list(format_options.keys()),
    )


def _apply_base_options(pipeline_options: Any) -> None:
    pipeline_options.enable_remote_services = False
    pipeline_options.allow_external_plugins = False
    timeout_s = settings.INGESTION_DOCLING_TIMEOUT_S
    if timeout_s and float(timeout_s) > 0:
        pipeline_options.document_timeout = float(timeout_s)
    elif hasattr(pipeline_options, "document_timeout"):
        pipeline_options.document_timeout = None

    if settings.INGESTION_DOCLING_ARTIFACTS_PATH:
        pipeline_options.artifacts_path = settings.INGESTION_DOCLING_ARTIFACTS_PATH

    accelerator = getattr(pipeline_options, "accelerator_options", None)
    if accelerator is not None:
        accelerator.device = settings.INGESTION_DOCLING_DEVICE
        accelerator.num_threads = settings.INGESTION_DOCLING_NUM_THREADS

    _configure_ocr(pipeline_options)


def _apply_profile_options(pipeline_options: Any) -> None:
    profile = (settings.INGESTION_DOCLING_PROFILE or "balanced").strip().lower()

    if profile == "fast":
        pipeline_options.do_ocr = False
        _set_table_mode(pipeline_options, "fast")
        pipeline_options.do_formula_enrichment = False
        pipeline_options.do_code_enrichment = False
        pipeline_options.do_picture_classification = False
        pipeline_options.do_picture_description = False
        pipeline_options.do_chart_extraction = False
        pipeline_options.generate_picture_images = False
        pipeline_options.images_scale = 1.0
        return

    # balanced defaults
    pipeline_options.do_ocr = True
    _set_table_mode(pipeline_options, "accurate")
    pipeline_options.do_formula_enrichment = False
    pipeline_options.do_code_enrichment = False
    pipeline_options.do_picture_classification = False
    pipeline_options.do_picture_description = False
    pipeline_options.do_chart_extraction = False
    pipeline_options.images_scale = 1.0

    if profile == "high_fidelity":
        pipeline_options.do_formula_enrichment = True
        pipeline_options.do_code_enrichment = True
        pipeline_options.do_picture_classification = True
        pipeline_options.do_picture_description = True
        pipeline_options.do_chart_extraction = True
        pipeline_options.generate_picture_images = True
        pipeline_options.images_scale = max(
            2.0, float(getattr(pipeline_options, "images_scale", 1.0))
        )


def _apply_override_options(pipeline_options: Any) -> None:
    # Honor the OCR feature flag: disabling it overrides any profile-level setting.
    if not settings.FEATURE_OCR_ENABLED:
        pipeline_options.do_ocr = False

    _set_table_mode(pipeline_options, settings.INGESTION_DOCLING_TABLE_MODE)
    _set_table_cell_matching(
        pipeline_options,
        settings.INGESTION_DOCLING_TABLE_CELL_MATCHING,
    )

    _set_optional_bool(
        pipeline_options,
        "do_formula_enrichment",
        settings.INGESTION_DOCLING_FORMULA_ENRICHMENT,
    )
    _set_optional_bool(
        pipeline_options,
        "do_code_enrichment",
        settings.INGESTION_DOCLING_CODE_ENRICHMENT,
    )
    _set_optional_bool(
        pipeline_options,
        "generate_picture_images",
        settings.INGESTION_DOCLING_PICTURE_IMAGES,
    )
    _set_optional_bool(
        pipeline_options,
        "do_picture_classification",
        settings.INGESTION_DOCLING_PICTURE_CLASSIFICATION,
    )
    _set_optional_bool(
        pipeline_options,
        "do_picture_description",
        settings.INGESTION_DOCLING_PICTURE_DESCRIPTION,
    )
    _set_optional_bool(
        pipeline_options,
        "do_chart_extraction",
        settings.INGESTION_DOCLING_CHART_EXTRACTION,
    )

    if (
        pipeline_options.generate_picture_images
        and getattr(pipeline_options, "images_scale", 1.0) < 1.0
    ):
        pipeline_options.images_scale = 1.0


def _configure_ocr(pipeline_options: Any) -> None:
    raw_langs = (settings.INGESTION_DOCLING_OCR_LANGS or "").strip()
    langs = [lang.strip() for lang in raw_langs.split(",") if lang.strip()]

    ocr_options = getattr(pipeline_options, "ocr_options", None)
    if ocr_options is not None and hasattr(ocr_options, "lang"):
        ocr_options.lang = langs

    raw_engine = (settings.INGESTION_DOCLING_OCR_ENGINE or "").strip().lower()
    if (
        raw_engine
        and raw_engine != "auto"
        and ocr_options is not None
        and hasattr(ocr_options, "kind")
    ):
        ocr_options.kind = raw_engine


def _set_table_mode(pipeline_options: Any, mode: str) -> None:
    table_options = getattr(pipeline_options, "table_structure_options", None)
    if table_options is None:
        return

    target_mode = (mode or "accurate").strip().lower()
    try:
        from docling.datamodel.pipeline_options import TableFormerMode

        table_options.mode = (
            TableFormerMode.FAST if target_mode == "fast" else TableFormerMode.ACCURATE
        )
    except Exception:
        # Keep compatibility if enum path changes across Docling versions.
        table_options.mode = "fast" if target_mode == "fast" else "accurate"


def _set_table_cell_matching(pipeline_options: Any, enabled: bool) -> None:
    table_options = getattr(pipeline_options, "table_structure_options", None)
    if table_options is None:
        return
    if hasattr(table_options, "do_cell_matching"):
        table_options.do_cell_matching = bool(enabled)


def _set_optional_bool(pipeline_options: Any, field_name: str, value: Any) -> None:
    if value is None:
        return
    setattr(pipeline_options, field_name, bool(value))
