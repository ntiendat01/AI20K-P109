"""Deterministic Total Cost of Ownership (TCO) models for models_v1."""

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from src.models_v1.common import ContractModel, Money, Quantity, VatRate


class TCOCalculationStatus(StrEnum):
    """Status indicating whether TCO was successfully calculated or has missing data."""

    CALCULATED = "calculated"
    MISSING_DATA = "missing_data"


class TCOBreakdownItem(ContractModel):
    """Deterministic TCO operands and line total for one item.

    Formula: item_tco = (unit_price * quantity + surcharges) * (1 + vat_rate)
    """

    item_name: str = Field(min_length=1)
    quantity: Quantity
    unit_price: Money
    subtotal: Money
    surcharges: Money = Field(default=Decimal("0.00"))
    vat_rate: VatRate
    vat_amount: Money
    item_tco: Money


class TCOResult(ContractModel):
    """Supplier-level Total Cost of Ownership calculation and breakdown.

    Invariants:
    - If status == 'calculated': total_tco must be present and missing_fields empty.
    - If status == 'missing_data': total_tco is None.
    """

    supplier_id: str = Field(min_length=1)
    quotation_revision_id: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    subtotal: Money
    total_surcharges: Money = Field(default=Decimal("0.00"))
    total_vat: Money
    total_tco: Money | None = None
    status: TCOCalculationStatus
    missing_fields: list[str] = Field(default_factory=list)
    breakdown: list[TCOBreakdownItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_tco_status(self) -> "TCOResult":
        if self.status == TCOCalculationStatus.CALCULATED:
            if self.total_tco is None:
                raise ValueError("calculated status requires total_tco")
            if self.missing_fields:
                raise ValueError("calculated status cannot have missing_fields")
        elif self.status == TCOCalculationStatus.MISSING_DATA:
            if self.total_tco is not None:
                raise ValueError("missing_data status must have total_tco as None")
        return self


__all__ = [
    "TCOBreakdownItem",
    "TCOCalculationStatus",
    "TCOResult",
]
