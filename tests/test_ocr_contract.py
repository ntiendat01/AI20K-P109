from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.infrastructure.ocr.contracts import OCRErrorCode, OCRErrorResponse, OCRResponse


def test_ocr_response_preserves_page_lines_and_confidence() -> None:
    response = OCRResponse.model_validate(
        {
            "request_id": "request-123",
            "document_sha256": "a" * 64,
            "engine": "paddleocr",
            "model_version": "PP-OCRv3",
            "pages": [
                {
                    "page_number": 1,
                    "raw_text": "Báo giá",
                    "lines": [{"text": "Báo giá", "confidence": 0.98}],
                }
            ],
        }
    )

    assert response.schema_version == "v1"
    assert response.pages[0].lines[0].confidence == 0.98


def test_ocr_response_rejects_invalid_document_checksum() -> None:
    with pytest.raises(ValidationError):
        OCRResponse.model_validate(
            {
                "request_id": "request-123",
                "document_sha256": "not-a-checksum",
                "engine": "paddleocr",
                "model_version": "PP-OCRv3",
            }
        )


def test_ocr_error_contract_marks_retryable_failures() -> None:
    error = OCRErrorResponse(
        request_id="request-123",
        code=OCRErrorCode.SERVICE_UNAVAILABLE,
        detail="OCR service is unavailable.",
        retryable=True,
    )

    assert error.code is OCRErrorCode.SERVICE_UNAVAILABLE
    assert error.retryable is True
