"""Versioned contracts shared by the core API and the OCR service."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class OCRErrorCode(StrEnum):
    """Stable error codes returned by the OCR boundary."""

    INVALID_DOCUMENT = "invalid_document"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    TOO_MANY_PAGES = "too_many_pages"
    SERVICE_BUSY = "service_busy"
    SERVICE_UNAVAILABLE = "service_unavailable"
    PROCESSING_FAILED = "processing_failed"


class OCRLine(BaseModel):
    """One recognized line and its engine-provided confidence."""

    text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class OCRPage(BaseModel):
    """Recognized content for one source page."""

    page_number: int = Field(ge=1)
    raw_text: str = ""
    lines: list[OCRLine] = Field(default_factory=list)


class OCRResponse(BaseModel):
    """The versioned response returned from ``POST /v1/ocr``."""

    schema_version: str = "v1"
    request_id: str = Field(min_length=1)
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    engine: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    pages: list[OCRPage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PDFExtractPage(BaseModel):
    page_number: int = Field(ge=1)
    method: Literal["text", "ocr"]
    text: str


class PDFExtractResponse(BaseModel):
    document_type: Literal["text", "scanned", "mixed"]
    pages: list[PDFExtractPage]
    ocr_lines: dict[int, list[OCRLine]] = Field(default_factory=dict)


class OCRErrorResponse(BaseModel):
    """Machine-readable failure payload for the OCR boundary."""

    schema_version: str = "v1"
    request_id: str = Field(min_length=1)
    code: OCRErrorCode
    detail: str = Field(min_length=1)
    retryable: bool
