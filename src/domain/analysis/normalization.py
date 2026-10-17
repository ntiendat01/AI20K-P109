"""Schemas emitted by deterministic unit and currency normalization."""

from pydantic import AliasChoices, Field

from src.domain.common import ContractModel, Quantity
from src.domain.quotation.extraction import RawExtraction


class NormalizedLine(RawExtraction):
    """Represent one confirmed quotation line converted to PR target units."""

    normalized_quantity: Quantity | None = None
    normalized_uom: str | None = None
    normalized_unit_price: float | None = Field(
        default=None, ge=0, validation_alias=AliasChoices("normalized_unit_price", "normalized_price")
    )
    normalized_currency: str | None = None
    requires_manual_conversion: bool = Field(
        default=False, validation_alias=AliasChoices("requires_manual_conversion", "needs_manual_conversion")
    )
    conversion_note: str | None = None


class NormalizedQuotation(ContractModel):
    """Group normalized lines for one supplier and unresolved conversions."""

    supplier_id: str = Field(min_length=1)
    items: list[NormalizedLine]
    has_manual_conversion: bool = False


DataNormalized = NormalizedQuotation
__all__ = ["DataNormalized", "NormalizedLine", "NormalizedQuotation"]
