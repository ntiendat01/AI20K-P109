"""Schemas emitted by the deterministic total-cost-of-ownership tool."""

from typing import Literal

from pydantic import AliasChoices, Field, model_validator

from src.models.common import ContractModel, Quantity


class TCOItem(ContractModel):
    """Expose deterministic TCO operands and result for one quotation item."""

    item_name: str = Field(default="", validation_alias=AliasChoices("item_name", "product_name"))
    quantity: Quantity | None = None
    unit_price: float | None = Field(default=None, ge=0)
    subtotal: float = Field(default=0, ge=0)
    surcharges: float = Field(default=0, ge=0)
    vat_rate: float = Field(default=0, ge=0, le=1)
    vat_included: bool = Field(default=False, validation_alias=AliasChoices("vat_included", "is_vat_included"))
    item_tco: float | None = Field(default=None, ge=0)


class TCOResult(ContractModel):
    """Aggregate calculated costs or missing-data state for one supplier."""

    supplier_id: str
    items_tco: list[TCOItem] = Field(default_factory=list)
    subtotal: float = Field(default=0, ge=0)
    total_surcharges: float = Field(default=0, ge=0)
    total_vat: float = Field(default=0, ge=0)
    total_tco: float | None = Field(default=None, ge=0)
    status: Literal["calculated", "missing_data"]
    missing_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_calculation_status(self) -> "TCOResult":
        if self.status == "calculated" and (self.total_tco is None or self.missing_fields):
            raise ValueError("calculated TCO requires total_tco and no missing_fields")
        if self.status == "missing_data" and self.total_tco is not None:
            raise ValueError("missing-data TCO cannot contain total_tco")
        return self


__all__ = ["TCOItem", "TCOResult"]
