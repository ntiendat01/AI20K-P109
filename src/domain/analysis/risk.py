"""Schemas emitted by deterministic and rule-based risk analysis."""

from typing import Literal

from pydantic import Field

from src.domain.common import ContractModel
from src.domain.quotation.extraction import SourceReference


class RiskFlag(ContractModel):
    """Describe one explainable supplier risk with severity and source."""

    supplier_id: str
    risk_type: str
    severity: Literal["info", "warning", "error"]
    message: str
    detail: dict[str, object] = Field(default_factory=dict)
    source: SourceReference | None = None


__all__ = ["RiskFlag"]
