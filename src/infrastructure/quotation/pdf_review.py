"""Authenticated quotation review previews rendered by the OCR service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Never

from src.infrastructure.ocr.client import OCRServiceError, RemoteOCRClient


def _source_bytes(source_path: Path) -> bytes:
    if source_path.suffix.lower() != ".pdf":
        raise ValueError("Chỉ có thể đối chiếu trực quan với file PDF.")
    try:
        return source_path.read_bytes()
    except OSError as error:
        raise ValueError("Không thể mở PDF gốc để đối chiếu.") from error


def _as_input_error(error: OCRServiceError) -> Never:
    if not error.retryable:
        raise ValueError(str(error)) from error
    raise error


def build_review_preview(source_path: Path, items: list[Any]) -> dict[str, Any]:
    """Return page dimensions and source regions for quotation items."""
    payload = [
        {
            "product_code": getattr(item, "product_code", None),
            "product_name": getattr(item, "product_name", None),
        }
        for item in items
    ]
    try:
        return RemoteOCRClient.from_settings().review_preview(_source_bytes(source_path), payload)
    except OCRServiceError as error:
        _as_input_error(error)


def render_review_preview_page(source_path: Path, page_number: int) -> bytes:
    """Render one page while source files remain protected by the backend API."""
    try:
        return RemoteOCRClient.from_settings().render_review_preview_page(_source_bytes(source_path), page_number)
    except OCRServiceError as error:
        _as_input_error(error)
