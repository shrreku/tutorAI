import json
import logging
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.services.ingestion.ingestion_types import SectionData, split_markdown_sections

logger = logging.getLogger(__name__)


@dataclass
class DoclingConversionResult:
    """Normalized Docling conversion result for ingestion pipeline use."""

    source: str
    source_type: str
    status: str
    docling_document: Any
    sections: list[SectionData]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class DoclingAdapter:
    """Typed wrapper around Docling DocumentConverter."""

    def __init__(self) -> None:
        self._converter = None
        self._active_profile = settings.INGESTION_DOCLING_PROFILE

    async def convert(self, source: str) -> DoclingConversionResult:
        """Convert local path or URL source to a normalized conversion result."""
        converter = self._get_converter()

        source_type = "url" if self._is_url(source) else "file"
        conversion = converter.convert(source=source, raises_on_error=False)

        status = self._normalize_status(getattr(conversion, "status", None))
        warnings = self._collect_messages(conversion, "warnings")
        errors = self._collect_messages(conversion, "errors")

        docling_document = getattr(conversion, "document", None)
        if docling_document is None:
            errors.append("Docling conversion returned no document")

        markdown_text = (
            self._export_markdown(docling_document) if docling_document else ""
        )
        sections = split_markdown_sections(markdown_text)
        if not sections and markdown_text.strip():
            sections = [
                SectionData(
                    heading=None,
                    page_start=None,
                    page_end=None,
                    text=markdown_text,
                    metadata={"source": "docling_markdown"},
                )
            ]

        metadata = {
            "profile": self._active_profile,
            "source": source,
            "source_type": source_type,
            "conversion_status": status,
            "warnings": warnings,
            "errors": errors,
            "sections_count": len(sections),
            "docling": self._extract_docling_metadata(conversion),
        }
        if source_type == "file":
            metadata.update(self._extract_file_metadata(source))

        return DoclingConversionResult(
            source=source,
            source_type=source_type,
            status=status,
            docling_document=docling_document,
            sections=sections,
            warnings=warnings,
            errors=errors,
            metadata=metadata,
        )

    def _get_converter(self):
        if self._converter is not None:
            return self._converter

        from app.services.ingestion.docling_config import build_docling_converter

        self._converter = build_docling_converter()
        return self._converter

    def _export_markdown(self, docling_document: Any) -> str:
        if docling_document is None:
            return ""

        for method_name in (
            "export_to_markdown",
            "to_markdown",
            "export_to_text",
            "to_text",
        ):
            method = getattr(docling_document, method_name, None)
            if callable(method):
                try:
                    content = method()
                    if isinstance(content, str):
                        return content
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "Docling markdown export failed via %s: %s", method_name, exc
                    )

        return ""

    @staticmethod
    def _make_json_safe(obj: Any) -> Any:
        """Recursively convert non-JSON-serializable objects to safe representations."""
        if obj is None or isinstance(obj, (str, bool)):
            return obj
        if isinstance(obj, float):
            import math

            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        if isinstance(obj, int):
            return obj
        if isinstance(obj, PurePath):
            return str(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        if isinstance(obj, (set, frozenset)):
            return [DoclingAdapter._make_json_safe(v) for v in sorted(obj, key=str)]
        if isinstance(obj, dict):
            return {str(k): DoclingAdapter._make_json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [DoclingAdapter._make_json_safe(v) for v in obj]
        if hasattr(obj, "value"):  # Enum-like
            return str(obj.value)
        # Handle numpy scalars
        try:
            import numpy as np

            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                import math

                val = float(obj)
                return None if math.isnan(val) or math.isinf(val) else val
            if isinstance(obj, np.ndarray):
                return DoclingAdapter._make_json_safe(obj.tolist())
        except ImportError:
            pass
        # Last resort
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    def _extract_docling_metadata(self, conversion: Any) -> dict:
        # Keep only JSON-serializable metadata fields.
        metadata: dict[str, Any] = {}
        for key in (
            "input",
            "timings",
            "pages",
            "assembled",
            "confidence",
        ):
            value = getattr(conversion, key, None)
            if value is None:
                continue
            try:
                if hasattr(value, "model_dump"):
                    metadata[key] = self._make_json_safe(value.model_dump())
                elif hasattr(value, "dict"):
                    metadata[key] = self._make_json_safe(value.dict())
                elif isinstance(value, (dict, list, str, int, float, bool)):
                    metadata[key] = self._make_json_safe(value)
                else:
                    metadata[key] = str(value)
            except Exception:
                metadata[key] = str(value)
        return metadata

    def _normalize_status(self, status: Any) -> str:
        if status is None:
            return "unknown"
        if hasattr(status, "value"):
            return str(status.value)
        return str(status)

    def _collect_messages(self, conversion: Any, field_name: str) -> list[str]:
        value = getattr(conversion, field_name, None)
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _extract_file_metadata(self, source: str) -> dict:
        path = Path(source)
        if not path.exists():
            return {}
        return {
            "file_name": path.name,
            "file_size_bytes": path.stat().st_size,
        }

    def _is_url(self, source: str) -> bool:
        parsed = urlparse(source)
        return parsed.scheme in {"http", "https"}
