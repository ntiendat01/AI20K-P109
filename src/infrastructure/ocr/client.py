"""Typed client for the isolated OCR service.

This module is the only OCR transport used by the backend.  It deliberately
contains no inference dependency: PaddleOCR belongs to ``ocr/ocr_service``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx

from src.core.config import get_settings
from src.infrastructure.ocr.contracts import OCRErrorResponse, OCRPage, OCRResponse, PDFExtractResponse


class OCRClient(Protocol):
    """Convert one local document into the established OCR JSON payload."""

    def extract_text(self, document_path: str) -> str:
        """Return page text and line confidence for one document."""


class OCRServiceError(RuntimeError):
    """A failure returned by the OCR service boundary."""

    def __init__(self, detail: str, *, retryable: bool) -> None:
        super().__init__(detail)
        self.retryable = retryable


class RemoteOCRClient:
    """HTTP adapter for the isolated OCR service."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        service_token: str = "",
        max_upload_bytes: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._service_token = service_token
        self._max_upload_bytes = max_upload_bytes
        self._transport = transport

    @classmethod
    def from_settings(cls) -> RemoteOCRClient:
        settings = get_settings()
        if not settings.ocr_service_base_url:
            raise ValueError("OCR_SERVICE_BASE_URL phải được cấu hình.")
        return cls(
            base_url=settings.ocr_service_base_url,
            timeout_seconds=settings.ocr_service_timeout_seconds,
            service_token=settings.ocr_service_token,
            max_upload_bytes=settings.ocr_max_upload_bytes,
        )

    def extract_text(self, document_path: str) -> str:
        source = Path(document_path)
        try:
            document = source.read_bytes()
        except OSError as error:
            raise ValueError(f"Không thể đọc tài liệu OCR: {source.name}") from error
        return self.extract_bytes(document, source.name)

    def extract_bytes(self, document: bytes, filename: str) -> str:
        """Return the legacy serialized payload expected by the LLM intake."""
        return json.dumps(
            {"pages": [page.model_dump() for page in self.extract_pages(document, filename)]}, ensure_ascii=False
        )

    def extract_pages(self, document: bytes, filename: str) -> list[OCRPage]:
        """Return typed OCR pages without a serialize/parse round trip."""
        response = self._post_document("/v1/ocr", document, filename)
        try:
            payload = OCRResponse.model_validate(response.json())
        except (ValueError, TypeError) as error:
            raise OCRServiceError("OCR service trả response không hợp lệ.", retryable=True) from error
        return payload.pages

    def extract_pdf_document(self, document: bytes) -> PDFExtractResponse:
        response = self._post_document("/v1/pdf/extract", document, "document.pdf")
        try:
            return PDFExtractResponse.model_validate(response.json())
        except (ValueError, TypeError) as error:
            raise OCRServiceError("OCR service trả response PDF không hợp lệ.", retryable=True) from error

    def detect_pdf_type(self, document: bytes) -> str:
        value = self._json_field("/v1/pdf/type", document, "document_type")
        if value not in {"text", "scanned", "mixed"}:
            raise OCRServiceError("OCR service trả loại PDF không hợp lệ.", retryable=True)
        return value

    def native_pdf_text(self, document: bytes) -> str:
        return self._json_field("/v1/pdf/native-text", document, "text")

    def review_preview(self, document: bytes, items: list[dict[str, object]]) -> dict:
        response = self._post_document(
            "/v1/pdf/review-preview", document, "document.pdf",
            data={"items_json": json.dumps(items, ensure_ascii=False)},
        )
        try:
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("pages"), list) or not isinstance(payload.get("matches"), list):
                raise ValueError("Invalid preview")
            return payload
        except (ValueError, TypeError) as error:
            raise OCRServiceError("OCR service trả preview không hợp lệ.", retryable=True) from error

    def render_review_preview_page(self, document: bytes, page_number: int) -> bytes:
        response = self._post_document(f"/v1/pdf/review-preview/pages/{page_number}", document, "document.pdf")
        if response.headers.get("content-type", "").split(";")[0] != "image/png":
            raise OCRServiceError("OCR service trả ảnh preview không hợp lệ.", retryable=True)
        return response.content

    def _json_field(self, endpoint: str, document: bytes, field: str) -> str:
        response = self._post_document(endpoint, document, "document.pdf")
        try:
            value = response.json()[field]
            if not isinstance(value, str):
                raise TypeError(field)
            return value
        except (ValueError, TypeError, KeyError) as error:
            raise OCRServiceError("OCR service trả response PDF không hợp lệ.", retryable=True) from error

    def _post_document(
        self, endpoint: str, document: bytes, filename: str, *, data: dict[str, str] | None = None
    ) -> httpx.Response:
        if len(document) > self._max_upload_bytes:
            raise ValueError("Tài liệu vượt quá giới hạn kích thước OCR.")

        headers = {"X-Request-ID": str(uuid4())}
        if self._service_token:
            headers["X-OCR-Service-Token"] = self._service_token
        try:
            with httpx.Client(timeout=self._timeout_seconds, transport=self._transport) as client:
                response = client.post(
                    f"{self._base_url}{endpoint}",
                    headers=headers,
                    files={"document": (filename, document, _content_type(Path(filename).suffix))},
                    data=data,
                )
        except httpx.HTTPError as error:
            raise OCRServiceError("Không thể kết nối OCR service.", retryable=True) from error

        if response.is_error:
            raise _service_error(response)
        return response


def _content_type(suffix: str) -> str:
    normalized = suffix.lower()
    if normalized == ".pdf":
        return "application/pdf"
    if normalized == ".png":
        return "image/png"
    if normalized in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return "application/octet-stream"


def _service_error(response: httpx.Response) -> OCRServiceError:
    try:
        error = OCRErrorResponse.model_validate(response.json())
    except (ValueError, TypeError):
        return OCRServiceError(f"OCR service trả HTTP {response.status_code}.", retryable=response.status_code >= 500)
    return OCRServiceError(error.detail, retryable=error.retryable)
