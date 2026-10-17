"""Supplier comparison matrix models for agent contract models."""

from decimal import Decimal

from pydantic import Field

from src.domain.agent.common import ContractModel


class ComparisonCell(ContractModel):
    """A cell in the supplier comparison matrix representing a metric value and deviation."""

    value: str = Field(min_length=1)
    deviation_pct: Decimal | None = None
    highlight: bool = False
    note: str | None = None


class SupplierComparisonMatrix(ContractModel):
    """Cross-supplier comparison matrix across key procurement criteria."""

    suppliers: list[str] = Field(default_factory=list)
    criteria: list[str] = Field(default_factory=list)
    matrix: dict[str, dict[str, ComparisonCell]] = Field(default_factory=dict)
    means: dict[str, Decimal | None] = Field(default_factory=dict)
    deviation_threshold: Decimal = Field(default=Decimal("0.15"), ge=0, le=1)


__all__ = [
    "ComparisonCell",
    "SupplierComparisonMatrix",
]
