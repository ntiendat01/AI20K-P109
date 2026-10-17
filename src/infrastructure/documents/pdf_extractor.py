"""Extract page text, table cells and provenance from PDF documents."""

import json
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import pdfplumber

from src.domain.quotation.extraction import ExtractedPage
from src.infrastructure.ocr.client import OCRServiceError, RemoteOCRClient


@dataclass
class ExtractedDocument:
    document_type: str
    pages: list[ExtractedPage]
    tables: list[tuple[int, list[list[str]]]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ocr_lines: dict[int, list[dict[str, object]]] = field(default_factory=dict)


class PDFTextExtractor:
    """Text-first OCR adapter shared by synchronous and agent extraction."""

    def extract_text(self, document_path: str) -> str:
        source = Path(document_path)
        try:
            document = extract_pdf(source.read_bytes())
        except OSError as error:
            raise ValueError(f"Không thể đọc tài liệu OCR: {source.name}") from error
        return json.dumps(
            {
                "pages": [
                    {
                        "page_number": page.page_number,
                        "raw_text": page.text,
                        "lines": document.ocr_lines.get(page.page_number, []),
                    }
                    for page in document.pages
                ]
            },
            ensure_ascii=False,
        )


def extract_pdf(content: bytes) -> ExtractedDocument:
    if not content.startswith(b"%PDF-"):
        raise ValueError("File không phải PDF hợp lệ.")
    try:
        response = RemoteOCRClient.from_settings().extract_pdf_document(content)
    except OCRServiceError as error:
        if error.retryable:
            raise
        raise ValueError(str(error)) from error

    pages = [ExtractedPage(page_number=page.page_number, method=page.method, text=page.text) for page in response.pages]
    result = ExtractedDocument(
        document_type=response.document_type,
        pages=pages,
        ocr_lines={number: [line.model_dump() for line in lines] for number, lines in response.ocr_lines.items()},
    )
    if any(page.method == "text" for page in pages):
        try:
            with pdfplumber.open(BytesIO(content)) as pdf:
                for page_number, page in enumerate(pdf.pages, 1):
                    if pages[page_number - 1].method != "text":
                        continue
                    for table in page.extract_tables() or []:
                        rows = [[(cell or "").strip() for cell in row] for row in table]
                        if rows:
                            result.tables.append((page_number, rows))
        except Exception:
            # Page text is still useful; table extraction is best effort.
            result.warnings.append("Không đọc được bảng; đã dùng văn bản trên trang.")
    return result
