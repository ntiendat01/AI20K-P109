from __future__ import annotations

import json

import httpx
import pytest

from src.infrastructure.ocr.client import OCRServiceError, RemoteOCRClient


def _client(handler) -> RemoteOCRClient:  # type: ignore[no-untyped-def]
    return RemoteOCRClient(
        base_url="http://ocr",
        timeout_seconds=5,
        max_upload_bytes=1024,
        transport=httpx.MockTransport(handler),
    )


def test_remote_client_converts_contract_to_existing_ocr_payload(tmp_path) -> None:  # type: ignore[no-untyped-def]
    document = tmp_path / "quote.pdf"
    document.write_bytes(b"%PDF-1.7 test")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://ocr/v1/ocr"
        assert request.headers["x-request-id"]
        return httpx.Response(
            200,
            json={
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
            },
        )

    payload = json.loads(_client(handler).extract_text(str(document)))

    assert payload["pages"][0]["lines"][0]["confidence"] == 0.98


def test_remote_client_preserves_retryable_service_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    document = tmp_path / "quote.pdf"
    document.write_bytes(b"%PDF-1.7 test")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={
                "request_id": "request-123",
                "code": "service_unavailable",
                "detail": "OCR model is not ready.",
                "retryable": True,
            },
        )

    with pytest.raises(OCRServiceError, match="not ready") as error:
        _client(handler).extract_text(str(document))

    assert error.value.retryable is True


def test_remote_client_returns_typed_pages(tmp_path) -> None:  # type: ignore[no-untyped-def]
    document = tmp_path / "quote.png"
    document.write_bytes(b"image")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request_id": "request-123",
                "document_sha256": "a" * 64,
                "engine": "paddleocr",
                "model_version": "PP-OCRv3",
                "pages": [{"page_number": 1, "raw_text": "Báo giá", "lines": []}],
            },
        )

    pages = _client(handler).extract_pages(document.read_bytes(), document.name)

    assert pages[0].raw_text == "Báo giá"
