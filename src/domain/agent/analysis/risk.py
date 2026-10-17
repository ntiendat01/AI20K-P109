"""Risk assessment schemas for agent contract models."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from src.domain.agent.common import ContractModel


class RiskSeverity(StrEnum):
    """Severity level of an identified procurement risk."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskFlag(ContractModel):
    """An explainable risk identified for a specific supplier quotation."""

    supplier_id: str = Field(min_length=1)
    risk_type: str = Field(min_length=1)
    severity: RiskSeverity
    description: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class RiskAssessmentArtifact(ContractModel):
    """Artifact payload containing all risk flags identified across evaluated quotations."""

    quotation_revision_ids: list[str] = Field(min_length=1)
    risk_flags: list[RiskFlag] = Field(default_factory=list)


__all__ = [
    "RiskAssessmentArtifact",
    "RiskFlag",
    "RiskSeverity",
]
