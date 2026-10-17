"""Document aggregate and OCR representation schemas for agent contract models."""

from enum import StrEnum
from typing import Literal

from pydantic import Field

from src.domain.agent.common import ConfidenceScore, ContractModel, UtcDateTime


class DocumentStatus(StrEnum):
    """Lifecycle status of an uploaded document file."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class BlockKind(StrEnum):
    """Classification of an OCR block element."""

    TEXT = "text"
    TABLE_CELL = "table_cell"


class OcrEngine(StrEnum):
    """Supported OCR and PDF text extraction engines."""

    PADDLEOCR = "paddleocr"
    PYMUPDF = "pymupdf"


class Document(ContractModel):
    """Document entity storing immutable file metadata and storage references."""

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    pr_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    media_type: Literal["application/pdf"] = "application/pdf"
    byte_size: int = Field(ge=0)
    content_hash: str = Field(min_length=1)
    file_path: str = Field(exclude=True)  # Internal storage path, never exposed to client
    status: DocumentStatus = DocumentStatus.UPLOADED
    created_by: str = Field(min_length=1)
    created_at: UtcDateTime


class UploadedDocumentResponse(ContractModel):
    """Response returned upon successful document upload (POST /prs/{pr_id}/documents)."""

    document_id: str
    filename: str
    content_hash: str
    job_id: str
    status: Literal["queued", "uploaded", "processing"] = "queued"


class DocumentBlock(ContractModel):
    """An atomic text block or table cell extracted from OCR with spatial coordinates."""

    block_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    kind: BlockKind
    text: str
    bounding_box: tuple[float, float, float, float] | None = None
    confidence: ConfidenceScore | None = None


class DocumentPage(ContractModel):
    """A single page grouping extracted OCR blocks."""

    page_number: int = Field(ge=1)
    blocks: list[DocumentBlock] = Field(default_factory=list)


class DocumentRepresentation(ContractModel):
    """Immutable representation containing complete structured OCR output."""

    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    engine: OcrEngine
    engine_version: str = Field(min_length=1)
    pages: list[DocumentPage] = Field(default_factory=list)
    created_at: UtcDateTime


class DocumentBlockRecord(ContractModel):
    """Flat representation of an OCR block for database persistence."""

    id: str = Field(min_length=1)
    representation_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    block_id: str = Field(min_length=1)
    kind: BlockKind
    text: str
    bounding_box_json: tuple[float, float, float, float] | None = None
    confidence: ConfidenceScore | None = None


__all__ = [
    "BlockKind",
    "Document",
    "DocumentBlock",
    "DocumentBlockRecord",
    "DocumentPage",
    "DocumentRepresentation",
    "DocumentStatus",
    "OcrEngine",
    "UploadedDocumentResponse",
]
