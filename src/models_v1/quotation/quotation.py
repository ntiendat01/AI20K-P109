"""Quotation aggregate entity and confirmed revisions for models_v1."""

from enum import StrEnum

from pydantic import Field

from src.models_v1.common import ContractModel, Money, Quantity, UtcDateTime, VatRate


class QuotationStatus(StrEnum):
    """Aggregate lifecycle status of a Quotation."""

    EXTRACTING = "extracting"
    NEEDS_CONFIRMATION = "needs_confirmation"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class QuotationRevisionStatus(StrEnum):
    """Lifecycle status of an individual Quotation Revision."""

    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"


class QuotationItemRevision(ContractModel):
    """Immutable line item within a confirmed quotation revision."""

    id: str = Field(min_length=1)
    quotation_revision_id: str = Field(min_length=1)
    source_item_id: str | None = None
    product_name: str = Field(min_length=1)
    product_code: str | None = None
    unit: str = Field(min_length=1)
    quantity_decimal: Quantity
    unit_price_decimal: Money
    created_at: UtcDateTime


class QuotationRevision(ContractModel):
    """Immutable quotation revision formed exclusively from Buyer confirmation.

    Invariants:
    - Never mutated once confirmed. Subsequent confirms produce new revisions.
    - supplier_id is server-owned and immutable.
    """

    id: str = Field(min_length=1)
    quotation_id: str = Field(min_length=1)
    revision_no: int = Field(ge=1)
    status: QuotationRevisionStatus = QuotationRevisionStatus.CONFIRMED
    supplier_id: str = Field(min_length=1)
    supplier_name: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    vat_rate: VatRate
    vat_included: bool
    lead_time_days: int = Field(ge=0)
    warranty_months: int = Field(ge=0)
    payment_terms: str = Field(min_length=1)
    review_note: str | None = None
    confirmed_by: str = Field(min_length=1)
    confirmed_at: UtcDateTime
    schema_version: str = "1.0"
    items: list[QuotationItemRevision] = Field(default_factory=list)
    created_at: UtcDateTime


class Quotation(ContractModel):
    """Quotation aggregate root providing a stable identity across revisions."""

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    pr_id: str = Field(min_length=1)
    supplier_id: str | None = None
    document_id: str = Field(min_length=1)
    current_version_no: int = Field(default=1, ge=1)
    current_confirmed_revision_id: str | None = None
    status: QuotationStatus = QuotationStatus.NEEDS_CONFIRMATION
    created_at: UtcDateTime


class QuotationConfirmationResponse(ContractModel):
    """Response payload returned upon successful Buyer confirmation (201 Created)."""

    quotation_id: str
    revision: QuotationRevision


__all__ = [
    "Quotation",
    "QuotationConfirmationResponse",
    "QuotationItemRevision",
    "QuotationRevision",
    "QuotationRevisionStatus",
    "QuotationStatus",
]
