"""Render protected PDF review previews and locate extracted quotation rows.

The procurement UI needs to compare editable extraction rows with the visual
source.  The uploaded source remains protected behind the API, so this module
returns page geometry and rendered page images instead of exposing a public
file URL.  Text positioning is intentionally best-effort: scanned PDFs remain
reviewable even when a row cannot be located automatically.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import pymupdf as fitz

PREVIEW_SCALE = 1.5


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", without_marks.lower()).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in _normalise(value).split() if len(token) > 1}


def _page_lines(page: fitz.Page) -> list[tuple[fitz.Rect, str]]:
    """Collect visible text lines with their visual bounding boxes."""
    grouped: dict[tuple[int, int], list[tuple[float, float, float, float, str]]] = {}
    for x0, y0, x1, y1, word, block, line, _ in page.get_text("words", sort=True):
        grouped.setdefault((block, line), []).append((x0, y0, x1, y1, word))

    lines = []
    for words in grouped.values():
        x0 = min(word[0] for word in words)
        y0 = min(word[1] for word in words)
        x1 = max(word[2] for word in words)
        y1 = max(word[3] for word in words)
        lines.append((fitz.Rect(x0, y0, x1, y1), " ".join(word[4] for word in words)))
    return lines


def _row_region(page: fitz.Page, rect: fitz.Rect) -> dict[str, float]:
    """Extend a matched text line across the table so the whole row reads as selected."""
    horizontal_padding = min(18, page.rect.width * 0.04)
    top = max(page.rect.y0, rect.y0 - 4)
    bottom = min(page.rect.y1, rect.y1 + 4)
    return {
        "x": round(page.rect.x0 + horizontal_padding, 2),
        "y": round(top, 2),
        "width": round(max(1, page.rect.width - horizontal_padding * 2), 2),
        "height": round(max(1, bottom - top), 2),
    }


def _find_item_region(document: fitz.Document, item: Any) -> dict[str, float | int] | None:
    """Find the most confident visual line for one extracted item.

    A product code is the strongest cue.  If it is absent, compare the
    meaningful words in the extracted description with each PDF text line.
    Returning no match is preferable to highlighting an unrelated row.
    """
    product_code = _normalise(str(getattr(item, "product_code", "")))
    product_name = str(getattr(item, "product_name", ""))
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

            line_tokens = _tokens(line_text)
            overlap = len(name_tokens & line_tokens)
            coverage = overlap / len(name_tokens) if name_tokens else 0
            # A two-word product label can be enough, but only if it accounts
            # for most of the name.  This avoids a generic word like "Dell"
            # selecting the first unrelated row.
            if overlap >= 2 and coverage >= 0.6:
                candidates.append((coverage, page_number, rect))

    if not candidates:
        return None
    score, page_number, rect = max(candidates, key=lambda candidate: candidate[0])
    if score < 0.6:
        return None
    page = document[page_number - 1]
    return {"page": page_number, **_row_region(page, rect)}


def build_review_preview(source_path: Path, items: list[Any]) -> dict[str, Any]:
    """Return page dimensions and one optional source region per quotation item."""
    if source_path.suffix.lower() != ".pdf":
        raise ValueError("Chỉ có thể đối chiếu trực quan với file PDF.")
    try:
        document = fitz.open(source_path)
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError) as error:
        raise ValueError("Không thể mở PDF gốc để đối chiếu.") from error

    with document:
        if not document.page_count:
            raise ValueError("PDF gốc không có trang để hiển thị.")
        pages = [
            {"number": number, "width": round(page.rect.width, 2), "height": round(page.rect.height, 2)}
            for number, page in enumerate(document, 1)
        ]
        matches = [
            {"item_index": index, "region": _find_item_region(document, item)} for index, item in enumerate(items)
        ]
    return {"pages": pages, "matches": matches}


def render_review_preview_page(source_path: Path, page_number: int) -> bytes:
    """Render one source page as a PNG for the authenticated review viewer."""
    if source_path.suffix.lower() != ".pdf":
        raise ValueError("Chỉ có thể hiển thị preview cho file PDF.")
    try:
        document = fitz.open(source_path)
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError) as error:
        raise ValueError("Không thể mở PDF gốc để đối chiếu.") from error

    with document:
        if page_number < 1 or page_number > document.page_count:
            raise ValueError("Trang PDF không tồn tại.")
        pixmap = document[page_number - 1].get_pixmap(matrix=fitz.Matrix(PREVIEW_SCALE, PREVIEW_SCALE), alpha=False)
        return pixmap.tobytes("png")
