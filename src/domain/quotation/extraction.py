"""Schemas for machine-extracted quotation data before Buyer confirmation."""

from enum import StrEnum
from typing import Literal

from pydantic import AliasChoices, Field, model_validator

from src.domain.common import ConfidenceScore, ContractModel, Quantity


class ExtractionStatus(StrEnum):
    """Describe the lifecycle state of one document extraction run."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class SourceReference(ContractModel):
    """Trace an extracted value to its document location and OCR text."""

    document_id: str | None = None
    document_path: str | None = None
    filename: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    source_text: str | None = None
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def require_source_location(self) -> "SourceReference":
        if not any(
            (self.document_id, self.document_path, self.filename, self.page_number, self.source_text, self.bbox)
        ):
            raise ValueError("source reference must identify a document location")
        return self


class Surcharge(ContractModel):
    """Represent an ancillary charge extracted from a quotation document."""

    kind: Literal["shipping", "handling", "other", "hidden"] = "other"
    description: str | None = None
    amount: float = Field(ge=0)
    currency: str | None = None
    included_in_tco: bool = True
    source: SourceReference | None = None
    normalized_amount: float | None = Field(default=None, ge=0)
    normalized_currency: str | None = None
    requires_manual_conversion: bool = False


class RawExtraction(ContractModel):
    """Represent one unconfirmed quotation line emitted by extraction."""

    extraction_id: str = Field(min_length=1)
    source: SourceReference
    supplier_id: str | None = Field(
        default=None, validation_alias=AliasChoices("supplier_id", "supplier", "supplier_name")
    )
    item_name: str | None = Field(default=None, validation_alias=AliasChoices("item_name", "product_name"))
    unit_price: float | None = Field(default=None, ge=0)
    quantity: Quantity | None = None
    unit: str | None = Field(default=None, validation_alias=AliasChoices("unit", "uom"))
    currency: str | None = None
    vat_rate: float | None = Field(default=None, ge=0, le=1)
    vat_included: bool | None = Field(default=None, validation_alias=AliasChoices("vat_included", "is_vat_included"))
    surcharges: list[Surcharge] = Field(default_factory=list)
    warranty_months: int | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    lead_time_min: int | None = Field(default=None, ge=0)
    lead_time_max: int | None = Field(default=None, ge=0)
    lead_time_unit: str | None = None
    confidence_score: ConfidenceScore = 0
    field_confidence: dict[str, ConfidenceScore] = Field(default_factory=dict)
    field_needs_confirmation: dict[str, bool] = Field(default_factory=dict)
    needs_confirmation: bool = False
    confirmed_by_human: bool = False
    extraction_error: str | None = None

    @model_validator(mode="after")
    def validate_lead_time_range(self) -> "RawExtraction":
        if (
            self.lead_time_min is not None
            and self.lead_time_max is not None
            and self.lead_time_min > self.lead_time_max
        ):
            raise ValueError("lead_time_min must not exceed lead_time_max")
        return self

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "source" not in data:
            data["source"] = {"document_path": data.pop("document", None), "page_number": data.pop("page_number", None)}
        else:
            data.pop("document", None)
            data.pop("page_number", None)
        shipping_fee = data.pop("shipping_fee", None)
        if not data.get("surcharges") and shipping_fee is not None:
            data["surcharges"] = [
                {
                    "kind": "shipping",
                    "description": "Shipping fee",
                    "amount": shipping_fee,
                    "currency": data.get("currency"),
                }
            ]
        return data


class ExtractedQuotationItem(ContractModel):
    """Represent one loosely parsed item from OCR or native PDF text."""

    raw_name: str | None = None
    raw_description: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    total_price: float | None = None
    currency: str | None = None
    source_page: int | None = None


class ExtractedQuotation(ContractModel):
    """Group unconfirmed quotation header fields and parsed items."""

    supplier_name: str | None = None
    quotation_number: str | None = None
    quotation_date: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    discount: float | None = None
    vat_rate: float | None = None
    vat_amount: float | None = None
    grand_total: float | None = None
    items: list[ExtractedQuotationItem] = Field(default_factory=list)


class ExtractedPage(ContractModel):
    """Carry page-level source text and the method used to obtain it."""

    page_number: int = Field(ge=1)
    method: Literal["text", "ocr"]
    text: str


class ExtractionResult(ContractModel):
    """Report output, warnings, and failure state for one extraction."""

    file_name: str
    status: ExtractionStatus
    document_type: Literal["text", "scanned", "mixed"] | None = None
    quotation: ExtractedQuotation | None = None
    pages: list[ExtractedPage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class BatchExtractionResult(ContractModel):
    """Return extraction results for a batch of quotation documents."""

    quotations: list[ExtractionResult]


__all__ = [
    "BatchExtractionResult",
    "ExtractedPage",
    "ExtractedQuotation",
    "ExtractedQuotationItem",
    "ExtractionResult",
    "ExtractionStatus",
    "RawExtraction",
    "SourceReference",
    "Surcharge",
]
