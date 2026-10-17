from __future__ import annotations

import fitz

from src.infrastructure.documents.ocr_extractor import ocr_page
from src.infrastructure.ocr.contracts import OCRPage


def test_parser_uses_remote_ocr(monkeypatch) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((20, 20), "scanned source")

    class Remote:
        def extract_pages(self, image: bytes, filename: str) -> list[OCRPage]:
            assert image.startswith(b"\x89PNG")
            assert filename == "page.png"
            return [OCRPage(page_number=1, raw_text="Báo giá remote")]

    monkeypatch.setattr("src.infrastructure.documents.ocr_extractor.RemoteOCRClient.from_settings", lambda: Remote())

    try:
        assert ocr_page(page) == "Báo giá remote"
    finally:
        document.close()
