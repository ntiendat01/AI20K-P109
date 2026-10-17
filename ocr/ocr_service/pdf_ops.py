"""PDF text, page rendering and review geometry owned by the OCR service."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import pymupdf as fitz

from ocr.ocr_service.engine import OCREngine

PREVIEW_SCALE = 1.5


def has_meaningful_text(text: str) -> bool:
    return sum(character.isalnum() for character in text) >= 15


def extract_pdf(content: bytes, engine: OCREngine) -> dict[str, Any]:
    """Read native text first and OCR only nonblank image pages."""
    with fitz.open(stream=content, filetype="pdf") as document:
        pages: list[dict[str, Any]] = []
        kinds: set[str] = set()
        ocr_lines: dict[int, list[dict[str, Any]]] = {}
        for number, page in enumerate(document, 1):
            text = page.get_text(sort=True)
            if has_meaningful_text(text):
                method = "text"
            elif not page.get_images(full=True) and not page.get_drawings():
                method = "text"
                text = ""
            else:
                method = "ocr"
                image = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes("png")
                recognized = engine.extract(image, ".png")
                text = "\n".join(result.raw_text for result in recognized)
                ocr_lines[number] = [line.model_dump() for result in recognized for line in result.lines]
            kinds.add(method)
            pages.append({"page_number": number, "method": method, "text": text})

    if not any(page["text"].strip() for page in pages):
        raise ValueError("PDF không có nội dung có thể trích xuất.")
    document_type = "mixed" if len(kinds) > 1 else "text" if "text" in kinds else "scanned"
    return {"document_type": document_type, "pages": pages, "ocr_lines": ocr_lines}


def detect_pdf_type(content: bytes) -> str:
    with fitz.open(stream=content, filetype="pdf") as document:
        kinds = {has_meaningful_text(page.get_text()) for page in document}
    return "text" if kinds == {True} else "scanned" if kinds == {False} else "mixed"


def native_pdf_text(content: bytes) -> str:
    with fitz.open(stream=content, filetype="pdf") as document:
        return "\n".join(page.get_text(sort=True) for page in document)


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", without_marks.lower()).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in _normalise(value).split() if len(token) > 1}


def _page_lines(page: fitz.Page) -> list[tuple[fitz.Rect, str]]:
    grouped: dict[tuple[int, int], list[tuple[float, float, float, float, str]]] = {}
    for x0, y0, x1, y1, word, block, line, _ in page.get_text("words", sort=True):
        grouped.setdefault((block, line), []).append((x0, y0, x1, y1, word))
    lines = []
    for words in grouped.values():
        rect = fitz.Rect(
            min(word[0] for word in words),
            min(word[1] for word in words),
            max(word[2] for word in words),
            max(word[3] for word in words),
        )
        lines.append((rect, " ".join(word[4] for word in words)))
    return lines


def _row_region(page: fitz.Page, rect: fitz.Rect) -> dict[str, float]:
    padding = min(18, page.rect.width * 0.04)
    top = max(page.rect.y0, rect.y0 - 4)
    bottom = min(page.rect.y1, rect.y1 + 4)
    return {
        "x": round(page.rect.x0 + padding, 2),
        "y": round(top, 2),
        "width": round(max(1, page.rect.width - padding * 2), 2),
        "height": round(max(1, bottom - top), 2),
    }


def _find_item_region(document: fitz.Document, item: dict[str, Any]) -> dict[str, float | int] | None:
    product_code = _normalise(str(item.get("product_code") or ""))
    product_name = str(item.get("product_name") or "")
    name_normalised = _normalise(product_name)
    name_tokens = _tokens(product_name)
    candidates: list[tuple[float, int, fitz.Rect]] = []
    for page_number, page in enumerate(document, 1):
        for rect, line_text in _page_lines(page):
            line_normalised = _normalise(line_text)
            if not line_normalised:
                continue
            if len(product_code) >= 3 and product_code in line_normalised:
                candidates.append((3.0, page_number, rect))
                continue
            if len(name_normalised) >= 5 and name_normalised in line_normalised:
                candidates.append((2.0, page_number, rect))
                continue
            overlap = len(name_tokens & _tokens(line_text))
            coverage = overlap / len(name_tokens) if name_tokens else 0
            if overlap >= 2 and coverage >= 0.6:
                candidates.append((coverage, page_number, rect))
    if not candidates:
        return None
    score, page_number, rect = max(candidates, key=lambda candidate: candidate[0])
    if score < 0.6:
        return None
    return {"page": page_number, **_row_region(document[page_number - 1], rect)}


def build_review_preview(content: bytes, items: list[dict[str, Any]]) -> dict[str, Any]:
    with fitz.open(stream=content, filetype="pdf") as document:
        pages = [
            {"number": number, "width": round(page.rect.width, 2), "height": round(page.rect.height, 2)}
            for number, page in enumerate(document, 1)
        ]
        matches = [
            {"item_index": index, "region": _find_item_region(document, item)}
            for index, item in enumerate(items)
        ]
    return {"pages": pages, "matches": matches}


def render_review_preview_page(content: bytes, page_number: int) -> bytes:
    with fitz.open(stream=content, filetype="pdf") as document:
        if page_number < 1 or page_number > document.page_count:
            raise ValueError("Trang PDF không tồn tại.")
        pixmap = document[page_number - 1].get_pixmap(matrix=fitz.Matrix(PREVIEW_SCALE, PREVIEW_SCALE), alpha=False)
        return pixmap.tobytes("png")
