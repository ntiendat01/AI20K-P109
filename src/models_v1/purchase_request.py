"""Purchase Request domain aggregate and command schemas for models_v1."""

from datetime import date
from enum import StrEnum

from pydantic import Field

from src.models_v1.common import ContractModel, Money, Quantity, UtcDateTime


class PurchaseRequestStatus(StrEnum):
    """Lifecycle status of a Purchase Request per contract specifications."""

    DRAFT = "draft"
    AWAITING_QUOTATION = "awaiting_quotation"
    COMPARING = "comparing"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class CreatePurchaseRequestCommand(ContractModel):
    """Payload to create a new purchase request."""

    code: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    category: str = Field(min_length=1, max_length=500)
    requested_quantity: Quantity
    requested_uom: str = Field(min_length=1, max_length=50)
    target_currency: str = Field(min_length=1, max_length=10)
    estimated_budget: Money
    delivery_due_date: date


class UpdatePurchaseRequestCommand(ContractModel):
    """Payload to update an editable draft purchase request."""

    category: str = Field(min_length=1, max_length=500)
    requested_quantity: Quantity
    requested_uom: str = Field(min_length=1, max_length=50)
    target_currency: str = Field(min_length=1, max_length=10)
    estimated_budget: Money
    delivery_due_date: date


class PurchaseRequest(ContractModel):
    """PurchaseRequest aggregate entity owning the procurement requirement lifecycle."""

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    code: str = Field(min_length=1)
    creator_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    requested_quantity: Quantity
    requested_uom: str = Field(min_length=1)
    target_currency: str = Field(min_length=1)
    estimated_budget: Money
    delivery_due_date: date
    status: PurchaseRequestStatus = PurchaseRequestStatus.DRAFT
    version: int = Field(default=1, ge=1)
    created_at: UtcDateTime
    updated_at: UtcDateTime


__all__ = [
    "CreatePurchaseRequestCommand",
    "PurchaseRequest",
    "PurchaseRequestStatus",
    "UpdatePurchaseRequestCommand",
]
