"""Deterministic unit and currency normalization models for models_v1."""

from enum import StrEnum

from pydantic import Field

from src.models_v1.common import ContractModel, Money, Quantity


class NormalizationStatus(StrEnum):
    """Status indicating whether all items could be normalized or require manual mapping."""

    NORMALIZED = "normalized"
    NEEDS_MAPPING = "needs_mapping"


class NormalizedItem(ContractModel):
    """An item with both its raw confirmed metrics and normalized target values.

    Invariant: If mapping or FX is missing, normalized fields are None (null),
    never silently defaulted or copied from source values.
    """

    source_quantity: Quantity
    source_uom: str = Field(min_length=1)
    source_unit_price: Money
    source_currency: str = Field(min_length=1)
    normalized_quantity: Quantity | None = None
    normalized_uom: str | None = None
    normalized_unit_price: Money | None = None
    normalized_currency: str | None = None
    rule_id: str | None = None


class NormalizedQuotationArtifact(ContractModel):
    """Artifact payload representing the normalized commercial terms of one quotation."""

    quotation_revision_id: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    status: NormalizationStatus
    items: list[NormalizedItem] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


__all__ = [
    "NormalizationStatus",
    "NormalizedItem",
    "NormalizedQuotationArtifact",
]
