import io
import math
import re
import zipfile
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

from pypdf import PdfReader


def estimate_page_count_from_bytes(filename: str, file_bytes: bytes) -> int:
    extension = Path(filename).suffix.lower()
    try:
        if extension == ".pdf":
            return _count_pdf_pages(file_bytes)
        if extension in {".pptx", ".ppt", ".key"}:
            return _count_presentation_pages(file_bytes)
        if extension in {".docx", ".docm", ".doc", ".rtf"}:
            return _count_word_pages(file_bytes)
        if extension in {".xlsx", ".xls"}:
            return _count_workbook_pages(file_bytes)
        if extension in {
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".webp",
            ".tif",
            ".tiff",
            ".svg",
        }:
            return 1
        if extension in {
            ".md",
            ".txt",
            ".html",
            ".htm",
            ".xml",
            ".csv",
            ".tsv",
            ".epub",
        }:
            return _estimate_textual_pages(file_bytes)
    except Exception:
        return _heuristic_fallback(file_bytes, extension)
    return _heuristic_fallback(file_bytes, extension)


def estimate_page_count_from_path(path: str, filename: Optional[str] = None) -> int:
    file_path = Path(path)
    with file_path.open("rb") as handle:
        return estimate_page_count_from_bytes(filename or file_path.name, handle.read())


def _count_pdf_pages(file_bytes: bytes) -> int:
    reader = PdfReader(io.BytesIO(file_bytes))
    return max(len(reader.pages), 1)


def _count_presentation_pages(file_bytes: bytes) -> int:
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
        slide_names = [
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        ]
    return max(len(slide_names), 1)


def _count_word_pages(file_bytes: bytes) -> int:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            raw = archive.read("docProps/app.xml")
        root = ElementTree.fromstring(raw)
        for elem in root.iter():
            if elem.tag.endswith("Pages") and elem.text:
                value = int(elem.text)
                if value > 0:
                    return value
    except Exception:
        pass
    text_like = file_bytes.decode("utf-8", errors="ignore")
    word_count = len(re.findall(r"\w+", text_like))
    if word_count > 0:
        return max(1, math.ceil(word_count / 500))
    return _heuristic_fallback(file_bytes, ".docx")


def _count_workbook_pages(file_bytes: bytes) -> int:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            sheet_names = [
                name
                for name in archive.namelist()
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            ]
        if sheet_names:
            return len(sheet_names)
    except Exception:
        pass
    return max(1, math.ceil(len(file_bytes) / 80_000))


def _estimate_textual_pages(file_bytes: bytes) -> int:
    text = file_bytes.decode("utf-8", errors="ignore")
    lines = [line for line in text.splitlines() if line.strip()]
    if lines:
        return max(1, math.ceil(len(lines) / 45))
    words = len(re.findall(r"\w+", text))
    if words:
        return max(1, math.ceil(words / 500))
    return _heuristic_fallback(file_bytes, ".txt")


def _heuristic_fallback(file_bytes: bytes, extension: str) -> int:
    size = max(len(file_bytes), 1)
    per_page = 150_000 if extension == ".pdf" else 60_000
    return max(1, math.ceil(size / per_page))
