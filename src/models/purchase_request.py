"""Schemas for purchase-request commands and current business state."""

from datetime import date
from enum import StrEnum

from pydantic import Field

from src.models.common import ContractModel, Money, Quantity, UtcDateTime


class PRStatus(StrEnum):
    """Describe the purchase-request lifecycle."""

    DRAFT = "draft"
    AWAITING_QUOTATION = "awaiting_quotation"
    COMPARING = "comparing"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class PRMetadata(ContractModel):
    """Metadata for a purchase request."""

    budget: Money | None = None
    delivery_time: date | None = None


class PRItem(ContractModel):
    """An item in a purchase request."""

    item_id: str | None = None
    order_index: int
    product_name: str = Field(min_length=1)
    quantity: Quantity
    unit: str = Field(min_length=1)
    notes: str | None = None


class CreatePurchaseRequest(ContractModel):
    """Validate the primary command that creates a purchase request."""

    code: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    category: str = Field(min_length=3, max_length=500)
    requested_quantity: Quantity
    requested_uom: str = Field(min_length=1)
    target_currency: str = Field(min_length=1)
    estimated_budget: Money
    delivery_due_date: date
    metadata: PRMetadata | None = None
    items: list[PRItem] = Field(default_factory=list)


class UpdatePurchaseRequest(ContractModel):
    """Validate PR fields editable before quotation processing begins."""

    category: str = Field(min_length=3, max_length=500)
    requested_quantity: Quantity
    requested_uom: str = Field(min_length=1)
    target_currency: str = Field(min_length=1)
    estimated_budget: Money
    delivery_due_date: date
    metadata: PRMetadata | None = None
    items: list[PRItem] = Field(default_factory=list)


class PurchaseRequest(ContractModel):
    """Represent the current purchase-request business state."""

    id: str
    tenant_id: str
    code: str
    creator_id: str
    creator_name: str
    category: str
    requested_quantity: Quantity
    requested_uom: str
    target_currency: str
    estimated_budget: Money
    delivery_due_date: date
    metadata: PRMetadata | None = None
    items: list[PRItem] = Field(default_factory=list)
    status: PRStatus
    quotation_count: int = 0
    rejection_reason: str | None = None
    po_id: str | None = None
    version: int = Field(ge=1)
    created_at: UtcDateTime
    updated_at: UtcDateTime


PurchaseRequestCreate = CreatePurchaseRequest
PurchaseRequestUpdate = UpdatePurchaseRequest
__all__ = [
    "CreatePurchaseRequest",
    "PRStatus",
    "PRMetadata",
    "PRItem",
    "PurchaseRequest",
    "PurchaseRequestCreate",
    "PurchaseRequestUpdate",
    "UpdatePurchaseRequest",
]
