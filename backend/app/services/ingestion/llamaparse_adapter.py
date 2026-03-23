import asyncio
import json
import logging
import math
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.ingestion.ingestion_types import SectionData, split_markdown_sections

logger = logging.getLogger(__name__)


@dataclass
class LlamaParseConversionResult:
    source: str
    source_type: str
    status: str
    sections: list[SectionData]
    parser_job_id: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class LlamaParseAdapter:
    def __init__(self) -> None:
        self._api_key = (settings.LLAMAPARSE_API_KEY or "").strip()
        self._base_url = settings.LLAMAPARSE_API_BASE_URL.rstrip("/")
        self._tier = (settings.LLAMAPARSE_TIER or "agentic_plus").strip()
        self._version = (settings.LLAMAPARSE_VERSION or "latest").strip()
        self._poll_interval_s = max(
            float(settings.LLAMAPARSE_POLL_INTERVAL_S or 2.0), 0.25
        )
        self._poll_timeout_s = max(int(settings.LLAMAPARSE_POLL_TIMEOUT_S or 900), 30)

    async def convert(self, source: str) -> LlamaParseConversionResult:
        if not self._api_key:
            raise RuntimeError("LLAMAPARSE_API_KEY is required for ingestion parsing")

        source_type = "url" if self._is_url(source) else "file"
        source_label = source if source_type == "url" else Path(source).name
        logger.info(
            "LlamaParse convert starting for %s source %s",
            source_type,
            source_label,
        )
        async with httpx.AsyncClient(
            timeout=self._poll_timeout_s, follow_redirects=True
        ) as client:
            if source_type == "url":
                job_id = await self._start_parse_for_url(client, source)
            else:
                job_id = await self._start_parse_for_file_upload(client, source)
            result_payload = await self._poll_result(client, job_id)

        metadata = result_payload.get("metadata") or {}
        job_payload = result_payload.get("job") or {}
        status = str(
            job_payload.get("status")
            or metadata.get("status")
            or result_payload.get("status")
            or "unknown"
        )
        warnings = self._collect_messages(metadata.get("warnings"))
        errors = self._collect_messages(metadata.get("errors"))
        sections = self._extract_sections(result_payload)
        llamaparse_metadata = {
            "job_id": job_id,
            "status": status,
            "job": self._make_json_safe(job_payload),
            "metadata": self._make_json_safe(metadata),
            "pages": self._extract_page_summaries(result_payload),
            "has_markdown": bool((result_payload.get("markdown") or {}).get("pages")),
            "has_text": bool((result_payload.get("text") or {}).get("pages")),
            "has_items": bool((result_payload.get("items") or {}).get("pages")),
            "has_json_output": result_payload.get("json_output") is not None,
        }

        payload_metadata = {
            "source": source,
            "source_type": source_type,
            "conversion_status": status,
            "sections_count": len(sections),
            "warnings": warnings,
            "errors": errors,
            "llamaparse": llamaparse_metadata,
        }
        if source_type == "file":
            payload_metadata.update(self._extract_file_metadata(source))

        if not sections:
            errors.append("LlamaParse returned no extractable sections")

        logger.info(
            "LlamaParse convert completed for job %s with status=%s sections=%s pages=%s warnings=%s errors=%s",
            job_id,
            status,
            len(sections),
            len(llamaparse_metadata["pages"]),
            len(warnings),
            len(errors),
        )

        return LlamaParseConversionResult(
            source=source,
            source_type=source_type,
            status=status,
            sections=sections,
            parser_job_id=job_id,
            warnings=warnings,
            errors=errors,
            metadata=payload_metadata,
        )

    async def _start_parse_for_file_upload(
        self, client: httpx.AsyncClient, source: str
    ) -> str:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        logger.info(
            "Uploading file to LlamaParse parse/upload: name=%s size_bytes=%s mime=%s",
            path.name,
            path.stat().st_size,
            mime_type,
        )
        with path.open("rb") as file_handle:
            response = await client.post(
                f"{self._base_url}/api/v2/parse/upload",
                headers=self._headers(accept_json=True, include_content_type=False),
                files={"file": (path.name, file_handle, mime_type)},
                data={"configuration": json.dumps(self._request_configuration())},
            )
        self._raise_for_status(response, "multipart file upload")
        payload = response.json()
        job_id = payload.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise RuntimeError("LlamaParse multipart upload did not return a job id")
        logger.info(
            "LlamaParse multipart upload accepted: job_id=%s name=%s tier=%s version=%s",
            job_id,
            path.name,
            self._tier,
            self._version,
        )
        return job_id

    async def _start_parse_for_url(
        self, client: httpx.AsyncClient, source_url: str
    ) -> str:
        return await self._start_parse(client, {"source_url": source_url})

    async def _start_parse(
        self, client: httpx.AsyncClient, payload: dict[str, Any]
    ) -> str:
        parse_mode = "url" if payload.get("source_url") else "file_id"
        response = await client.post(
            f"{self._base_url}/api/v2/parse/",
            headers=self._headers(),
            json={**payload, **self._request_configuration()},
        )
        self._raise_for_status(response, f"parse request ({parse_mode})")
        data = response.json()
        job_id = data.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise RuntimeError("LlamaParse parse request did not return a job id")
        logger.info(
            "LlamaParse parse job created: job_id=%s mode=%s tier=%s version=%s",
            job_id,
            parse_mode,
            self._tier,
            self._version,
        )
        return job_id

    async def _poll_result(
        self, client: httpx.AsyncClient, job_id: str
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + self._poll_timeout_s
        last_payload: dict[str, Any] | None = None
        last_status: str | None = None
        while True:
            response = await client.get(
                f"{self._base_url}/api/v2/parse/{job_id}",
                headers=self._headers(accept_json=True, include_content_type=False),
                params={
                    "expand": "markdown,text,items,metadata",
                },
            )
            self._raise_for_status(response, f"result poll for job {job_id}")
            payload = response.json()
            last_payload = payload if isinstance(payload, dict) else {}
            job_payload = last_payload.get("job") or {}
            status = str(
                job_payload.get("status")
                or (last_payload.get("metadata") or {}).get("status")
                or last_payload.get("status")
                or "PENDING"
            ).upper()
            if status != last_status:
                logger.info(
                    "LlamaParse poll status: job_id=%s status=%s", job_id, status
                )
                last_status = status
            if status == "COMPLETED":
                return last_payload
            if status in {"FAILED", "CANCELLED"}:
                message = (
                    job_payload.get("error_message")
                    or (last_payload.get("metadata") or {}).get("error_message")
                    or (last_payload.get("metadata") or {}).get("error")
                    or "LlamaParse job failed"
                )
                raise RuntimeError(str(message))
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"Timed out waiting for LlamaParse job {job_id}")
            await asyncio.sleep(self._poll_interval_s)

    def _request_configuration(self) -> dict[str, Any]:
        return {
            "tier": self._tier,
            "version": self._version,
            "input_options": self._build_input_options(),
            "output_options": self._build_output_options(),
            "processing_options": self._build_processing_options(),
        }

    def _raise_for_status(self, response: httpx.Response, action: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            logger.error(
                "LlamaParse %s failed with status=%s body=%s",
                action,
                response.status_code,
                response.text,
            )
            raise

    def _build_input_options(self) -> dict[str, Any]:
        return {
            "html": {
                "make_all_elements_visible": True,
                "remove_fixed_elements": True,
                "remove_navigation_elements": True,
            },
            "spreadsheet": {
                "detect_sub_tables_in_sheets": True,
                "force_formula_computation_in_sheets": True,
            },
            "presentation": {
                "out_of_bounds_content": True,
                "skip_embedded_data": False,
            },
        }

    def _build_output_options(self) -> dict[str, Any]:
        return {
            "markdown": {
                "annotate_links": True,
                "tables": {
                    "compact_markdown_tables": False,
                    "output_tables_as_markdown": True,
                    "merge_continued_tables": True,
                    "markdown_table_multiline_separator": "<br>",
                },
            },
            "extract_printed_page_number": True,
        }

    def _build_processing_options(self) -> dict[str, Any]:
        languages = [
            self._normalize_ocr_language_code(item)
            for item in (settings.INGESTION_DOCLING_OCR_LANGS or "eng").split(",")
            if item.strip()
        ]
        payload: dict[str, Any] = {
            "aggressive_table_extraction": True,
            "ignore": {
                "ignore_diagonal_text": True,
                "ignore_hidden_text": False,
                "ignore_text_in_image": not bool(settings.FEATURE_OCR_ENABLED),
            },
        }
        if settings.FEATURE_OCR_ENABLED:
            payload["ocr_parameters"] = {"languages": languages or ["en"]}
        return payload

    def _normalize_ocr_language_code(self, value: str) -> str:
        normalized = value.strip().lower().replace("-", "_")
        mapping = {
            "eng": "en",
            "english": "en",
            "spa": "es",
            "spanish": "es",
            "fra": "fr",
            "fre": "fr",
            "french": "fr",
            "deu": "de",
            "ger": "de",
            "german": "de",
            "ita": "it",
            "italian": "it",
            "por": "pt",
            "portuguese": "pt",
            "nld": "nl",
            "dut": "nl",
            "dutch": "nl",
            "rus": "ru",
            "russian": "ru",
            "jpn": "ja",
            "japanese": "ja",
            "kor": "ko",
            "korean": "ko",
            "chi_sim": "ch_sim",
            "chi_tra": "ch_tra",
            "zho": "ch_sim",
        }
        return mapping.get(normalized, normalized)

    def _extract_sections(self, result_payload: dict[str, Any]) -> list[SectionData]:
        markdown_payload = result_payload.get("markdown") or {}
        markdown_pages = markdown_payload.get("pages")
        sections: list[SectionData] = []
        if isinstance(markdown_pages, list) and markdown_pages:
            for page_entry in markdown_pages:
                if not isinstance(page_entry, dict):
                    continue
                page_number = self._coerce_int(
                    page_entry.get("page_number")
                    or page_entry.get("page")
                    or page_entry.get("number")
                )
                page_markdown = (
                    page_entry.get("markdown") or page_entry.get("text") or ""
                )
                if not isinstance(page_markdown, str) or not page_markdown.strip():
                    continue
                page_sections = split_markdown_sections(page_markdown)
                if not page_sections:
                    page_sections = [
                        SectionData(
                            heading=None,
                            page_start=page_number,
                            page_end=page_number,
                            text=page_markdown.strip(),
                            metadata={"source": "llamaparse_markdown_page"},
                        )
                    ]
                for section in page_sections:
                    section.metadata = {
                        **(section.metadata or {}),
                        "source": "llamaparse_markdown",
                    }
                    if page_number is not None:
                        section.page_start = page_number
                        section.page_end = page_number
                    sections.append(section)
            if sections:
                return sections

        fallback_markdown = markdown_payload.get("markdown")
        if isinstance(fallback_markdown, str) and fallback_markdown.strip():
            sections = split_markdown_sections(fallback_markdown)
            for section in sections:
                section.metadata = {
                    **(section.metadata or {}),
                    "source": "llamaparse_markdown",
                }
            if sections:
                return sections

        text_payload = result_payload.get("text") or {}
        text_pages = text_payload.get("pages")
        if isinstance(text_pages, list):
            for page_entry in text_pages:
                if not isinstance(page_entry, dict):
                    continue
                page_number = self._coerce_int(
                    page_entry.get("page_number")
                    or page_entry.get("page")
                    or page_entry.get("number")
                )
                page_text = page_entry.get("text") or ""
                if not isinstance(page_text, str) or not page_text.strip():
                    continue
                sections.append(
                    SectionData(
                        heading=f"Page {page_number}"
                        if page_number is not None
                        else None,
                        page_start=page_number,
                        page_end=page_number,
                        text=page_text.strip(),
                        metadata={"source": "llamaparse_text"},
                    )
                )
        return sections

    def _extract_page_summaries(
        self, result_payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        page_sources = []
        for field_name in ("markdown", "text", "items"):
            payload = result_payload.get(field_name) or {}
            pages = payload.get("pages")
            if isinstance(pages, list):
                page_sources.append((field_name, pages))
        page_map: dict[int, dict[str, Any]] = {}
        for source_name, pages in page_sources:
            for entry in pages:
                if not isinstance(entry, dict):
                    continue
                page_number = self._coerce_int(
                    entry.get("page_number") or entry.get("page") or entry.get("number")
                )
                if page_number is None:
                    continue
                page_summary = page_map.setdefault(
                    page_number, {"page_number": page_number}
                )
                if source_name == "markdown":
                    page_summary["has_markdown"] = bool(
                        entry.get("markdown") or entry.get("text")
                    )
                elif source_name == "text":
                    page_summary["has_text"] = bool(entry.get("text"))
                elif source_name == "items":
                    items = entry.get("items")
                    page_summary["item_count"] = (
                        len(items) if isinstance(items, list) else 0
                    )
        for page_number in sorted(page_map):
            summaries.append(page_map[page_number])
        return summaries

    def _headers(
        self, *, accept_json: bool = True, include_content_type: bool = True
    ) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if accept_json:
            headers["Accept"] = "application/json"
        if include_content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _collect_messages(self, value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return [str(value)]

    def _extract_file_metadata(self, source: str) -> dict[str, Any]:
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

    def _coerce_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _make_json_safe(obj: Any) -> Any:
        if obj is None or isinstance(obj, (str, bool)):
            return obj
        if isinstance(obj, float):
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
            return [LlamaParseAdapter._make_json_safe(v) for v in sorted(obj, key=str)]
        if isinstance(obj, dict):
            return {
                str(k): LlamaParseAdapter._make_json_safe(v) for k, v in obj.items()
            }
        if isinstance(obj, (list, tuple)):
            return [LlamaParseAdapter._make_json_safe(v) for v in obj]
        if hasattr(obj, "value"):
            return str(obj.value)
        try:
            import numpy as np

            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                val = float(obj)
                return None if math.isnan(val) or math.isinf(val) else val
            if isinstance(obj, np.ndarray):
                return LlamaParseAdapter._make_json_safe(obj.tolist())
        except ImportError:
            pass
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)
