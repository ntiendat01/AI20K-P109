"""Schemas emitted by deterministic supplier comparison."""

from pydantic import Field

from src.domain.common import ContractModel


class ComparisonCell(ContractModel):
    """Represent one supplier-metric value in the comparison matrix."""

    value: float | str
    deviation_pct: float | None = None
    highlight: bool = False
    note: str | None = None


class ComparisonMatrix(ContractModel):
    """Compare suppliers using TCO and normalized commercial facts."""

    suppliers: list[str] = Field(default_factory=list)
    criteria: list[str] = Field(default_factory=list)
    matrix: dict[str, dict[str, ComparisonCell]] = Field(default_factory=dict)
    means: dict[str, float | None] = Field(default_factory=dict)
    deviation_threshold: float = Field(default=0.15, ge=0, le=1)


__all__ = ["ComparisonCell", "ComparisonMatrix"]
