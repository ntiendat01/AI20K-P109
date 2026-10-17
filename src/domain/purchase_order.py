"""Schemas for draft purchase orders created after Manager approval."""

from enum import StrEnum

from src.domain.common import ContractModel, Money, UtcDateTime


class POStatus(StrEnum):
    """Describe the intentionally small lifecycle of a generated PO."""

    DRAFT = "draft"
    CANCELLED = "cancelled"


class PurchaseOrder(ContractModel):
    """Represent a draft PO traceable to the approved recommendation snapshot."""

    id: str
    tenant_id: str
    code: str
    pr_id: str
    approval_decision_id: str
    analysis_id: str
    snapshot_hash: str
    supplier_id: str
    quotation_revision_id: str
    subtotal: Money
    shipping_amount: Money | None
    tax_amount: Money
    total_amount: Money
    currency: str
    status: POStatus
    approver_id: str
    approved_at: UtcDateTime
    created_at: UtcDateTime


__all__ = ["POStatus", "PurchaseOrder"]
