"""Inspect PDF pages through the OCR service to select an extraction path."""

from pathlib import Path

from src.infrastructure.ocr.client import OCRServiceError, RemoteOCRClient


def detect_pdf_type(file_path: str) -> str:
    try:
        return RemoteOCRClient.from_settings().detect_pdf_type(Path(file_path).read_bytes())
    except OCRServiceError as error:
        if error.retryable:
            raise
        raise ValueError(str(error)) from error
