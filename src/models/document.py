"""Schemas describing an uploaded document and its OCR representation."""

from enum import StrEnum
from typing import Literal

from pydantic import Field

from src.models.common import ConfidenceScore, ContractModel, UtcDateTime


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class UploadedDocument(ContractModel):
    """Describe immutable metadata for one uploaded supplier document."""

    document_id: str
    tenant_id: str
    pr_id: str
    filename: str
    media_type: Literal["application/pdf"] = "application/pdf"
    byte_size: int = Field(ge=0)
    content_hash: str
    file_path: str = Field(exclude=True)
    status: DocumentStatus
    created_by: str
    created_at: UtcDateTime


class DocumentBlock(ContractModel):
    """Represent one traceable text or table-cell block produced by OCR."""

    block_id: str
    page_number: int = Field(ge=1)
    kind: Literal["text", "table_cell"]
    text: str
    bounding_box: tuple[float, float, float, float] | None = None
    confidence: ConfidenceScore | None = None


class DocumentPage(ContractModel):
    """Group OCR blocks that belong to the same source document page."""

    page_number: int = Field(ge=1)
    blocks: list[DocumentBlock] = Field(default_factory=list)


class DocumentRepresentation(ContractModel):
    """Carry the complete immutable OCR output consumed by extraction."""

    representation_id: str
    document_id: str
    pages: list[DocumentPage] = Field(default_factory=list)
    engine: Literal["paddleocr", "pymupdf"]
    engine_version: str
    created_at: UtcDateTime


class DocumentBlockRecord(ContractModel):
    """Persist one immutable OCR block belonging to a representation."""

    id: str
    representation_id: str
    page_number: int = Field(ge=1)
    block_id: str
    kind: Literal["text", "table_cell"]
    text: str
    bounding_box_json: tuple[float, float, float, float] | None = None
    confidence: ConfidenceScore | None = None
