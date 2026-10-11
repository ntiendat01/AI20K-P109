"""Inspect page content, rather than PDF metadata, to select an extraction path."""

import pymupdf as fitz


def has_meaningful_text(text: str) -> bool:
    # A page number or a tiny scan watermark is not a usable text layer.
    return sum(character.isalnum() for character in text) >= 15


def detect_pdf_type(file_path: str) -> str:
    try:
        with fitz.open(file_path) as document:
            if not document.page_count:
                raise ValueError("PDF không có trang.")
            kinds = {has_meaningful_text(page.get_text()) for page in document}
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError) as error:
        raise ValueError("PDF không hợp lệ hoặc bị hỏng.") from error
    if kinds == {True}:
        return "text"
    if kinds == {False}:
        return "scanned"
    return "mixed"
