"""Buyer HITL-1 quotation confirmation request models for models_v1."""

from pydantic import Field

from src.models_v1.common import ContractModel, Money, Quantity, VatRate


class ConfirmedItemPayload(ContractModel):
    """Line item confirmed by the Buyer during HITL-1 review."""

    source_item_id: str | None = None
    product_name: str = Field(min_length=1, max_length=500)
    product_code: str | None = Field(default=None, max_length=100)
    unit: str = Field(min_length=1, max_length=50)
    quantity: Quantity
    unit_price: Money


class QuotationConfirmationRequest(ContractModel):
    """Command payload sent by Buyer to confirm a quotation (POST /quotations/{id}/confirm).

    Invariants per contract:
    - Does NOT contain shipping cost (shipping cost is excluded from quotation contract).
    - supplier_id is server-owned and cannot be provided or altered by the client.
    - All money and quantity fields are formatted as decimal strings.
    """

    supplier_name: str = Field(min_length=1, max_length=200)
    currency: str = Field(min_length=1, max_length=10)
    vat_rate: VatRate
    vat_included: bool
    lead_time_days: int = Field(ge=0)
    warranty_months: int = Field(ge=0)
    payment_terms: str = Field(min_length=1, max_length=500)
    items: list[ConfirmedItemPayload] = Field(min_length=1)
    review_note: str | None = None


__all__ = [
    "ConfirmedItemPayload",
    "QuotationConfirmationRequest",
]
