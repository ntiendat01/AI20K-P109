"""Quotation extraction draft, validation, and field provenance models for agent contract models."""

from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from src.domain.agent.common import ConfidenceScore, ContractModel, UtcDateTime


class ExtractionStatus(StrEnum):
    """Lifecycle status of a machine extraction run."""

    EXTRACTED = "extracted"
    VALIDATED = "validated"
    FAILED = "failed"


class ValidationSeverity(StrEnum):
    """Severity of a validation issue."""

    WARNING = "warning"
    BLOCKING = "blocking"


class FieldSource(ContractModel):
    """Source provenance pointing to an exact OCR block in a document page."""

    document_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    block_id: str = Field(min_length=1)


class ExtractedFieldValue(ContractModel):
    """An individual extracted field paired with its confidence and provenance."""

    value: str | None = None
    confidence: ConfidenceScore | None = None
    source: FieldSource | None = None


class ExtractedItemField(ContractModel):
    """An individual line item within an extraction draft."""

    source_item_id: str = Field(min_length=1)
    product_name: ExtractedFieldValue
    product_code: ExtractedFieldValue | None = None
    unit: ExtractedFieldValue | None = None
    quantity: ExtractedFieldValue | None = None
    unit_price: ExtractedFieldValue


class ExtractionDraftPayload(ContractModel):
    """Unconfirmed structured payload extracted from document for Buyer review."""

    supplier_name: ExtractedFieldValue | None = None
    currency: ExtractedFieldValue | None = None
    vat_rate: ExtractedFieldValue | None = None
    vat_included: ExtractedFieldValue | None = None
    lead_time_days: ExtractedFieldValue | None = None
    warranty_months: ExtractedFieldValue | None = None
    payment_terms: ExtractedFieldValue | None = None
    items: list[ExtractedItemField] = Field(default_factory=list)


class ValidationIssue(ContractModel):
    """Validation issue detected in extraction, highlighting low-confidence or structural errors."""

    field_path: str = Field(min_length=1)
    code: str = Field(min_length=1)
    severity: ValidationSeverity
    confidence: ConfidenceScore | None = None
    details: dict[str, Any] | None = None


class ValidatedExtraction(ContractModel):
    """Result of extraction validation tool."""

    schema_valid: bool
    human_confirmation_required: Literal[True] = True
    issues: list[ValidationIssue] = Field(default_factory=list)


class QuotationExtraction(ContractModel):
    """QuotationExtraction aggregate entity representing one machine extraction attempt."""

    id: str = Field(min_length=1)
    quotation_id: str = Field(min_length=1)
    document_representation_id: str = Field(min_length=1)
    version_no: int = Field(ge=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    schema_valid: bool
    human_confirmation_required: Literal[True] = True
    applied_confidence_threshold: ConfidenceScore = Field(default=Decimal("0.80"))
    status: ExtractionStatus
    created_at: UtcDateTime


class ExtractedFieldRecord(ContractModel):
    """Persisted record for each extracted field for fine-grained audit and provenance."""

    id: str = Field(min_length=1)
    quotation_extraction_id: str = Field(min_length=1)
    source_item_id: str | None = None
    field_path: str = Field(min_length=1)
    raw_value: str | None = None
    parsed_value: Any = None
    confidence: ConfidenceScore
    document_id: str | None = None
    page_number: int | None = None
    block_id: str | None = None
    bounding_box: tuple[float, float, float, float] | None = None
    source_text: str | None = None


class QuotationReviewResponse(ContractModel):
    """Response returned by GET /quotations/{quotation_id} for HITL-1 review UI."""

    quotation_id: str
    status: str
    human_confirmation_required: Literal[True] = True
    confidence_threshold: ConfidenceScore = Field(default=Decimal("0.80"))
    draft_revision_no: int = Field(ge=1)
    extraction: ExtractionDraftPayload | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list)


__all__ = [
    "ExtractedFieldRecord",
    "ExtractedFieldValue",
    "ExtractedItemField",
    "ExtractionDraftPayload",
    "ExtractionStatus",
    "FieldSource",
    "QuotationExtraction",
    "QuotationReviewResponse",
    "ValidatedExtraction",
    "ValidationIssue",
    "ValidationSeverity",
]
