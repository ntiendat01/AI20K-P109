"""Extract page text, table cells and provenance from PDF documents."""

from dataclasses import dataclass, field
from io import BytesIO

import pdfplumber
import pymupdf as fitz

from src.extraction.detector import has_meaningful_text
from src.extraction.ocr_extractor import ocr_page
from src.models.quotation.extraction import ExtractedPage

MAX_PDF_PAGES = 10


@dataclass
class ExtractedDocument:
    document_type: str
    pages: list[ExtractedPage]
    tables: list[tuple[int, list[list[str]]]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def extract_pdf(content: bytes) -> ExtractedDocument:
    if not content.startswith(b"%PDF-"):
        raise ValueError("File không phải PDF hợp lệ.")
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError) as error:
        raise ValueError("PDF không hợp lệ hoặc bị hỏng.") from error
    with document:
        if not document.page_count:
            raise ValueError("PDF không có trang.")
        if document.page_count > MAX_PDF_PAGES:
            raise ValueError(f"PDF vượt quá giới hạn {MAX_PDF_PAGES} trang.")
        pages: list[ExtractedPage] = []
        kinds: set[str] = set()
        for number, page in enumerate(document, 1):
            text = page.get_text(sort=True)
            if has_meaningful_text(text):
                method = "text"
            elif not page.get_images(full=True) and not page.get_drawings():
                # Do not invoke OCR for a genuinely blank page.  The caller
                # can return an editable, warning-only review draft instead.
                method = "text"
                text = ""
            else:
                method = "ocr"
                text = ocr_page(page)
            kinds.add(method)
            pages.append(ExtractedPage(page_number=number, method=method, text=text))

    document_type = "mixed" if len(kinds) > 1 else "text" if "text" in kinds else "scanned"
    if not any(page.text.strip() for page in pages):
        raise ValueError("PDF không có nội dung có thể trích xuất.")

    result = ExtractedDocument(document_type=document_type, pages=pages)
    if "text" in kinds:
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
