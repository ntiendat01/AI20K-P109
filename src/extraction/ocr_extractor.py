"""Tesseract OCR for pages without a usable text layer."""

import shutil
import subprocess

import pymupdf as fitz

OCR_LANGUAGES = ("eng", "vie")


def ocr_page(page: fitz.Page) -> str:
    if shutil.which("tesseract") is None:
        raise ValueError("Tesseract OCR chưa được cài đặt.")
    try:
        available = subprocess.run(
            ["tesseract", "--list-langs"], capture_output=True, text=True, check=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("Không thể kiểm tra dữ liệu ngôn ngữ Tesseract.") from error
    if available.returncode:
        raise ValueError("Không thể kiểm tra dữ liệu ngôn ngữ Tesseract.")
    missing = [language for language in OCR_LANGUAGES if language not in available.stdout.split()]
    if missing:
        raise ValueError(f"Thiếu dữ liệu OCR Tesseract: {', '.join(missing)}.")
    image = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes("png")
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "+".join(OCR_LANGUAGES), "--psm", "6"],
            input=image,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("OCR thất bại khi xử lý trang PDF.") from error
    if result.returncode:
        raise ValueError("OCR thất bại khi xử lý trang PDF.")
    return result.stdout.decode("utf-8", errors="replace")
