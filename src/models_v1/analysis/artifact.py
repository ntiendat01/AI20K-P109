"""Analysis artifact envelope schema for models_v1."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from src.models_v1.common import ContractModel, UtcDateTime


class ArtifactType(StrEnum):
    """Allowed artifact types produced during procurement analysis."""

    NORMALIZATION = "normalization"
    TCO = "tco"
    RISK = "risk"
    COMPARISON = "comparison"
    DECISION = "decision"


class AnalysisArtifact(ContractModel):
    """Common envelope for versioned, immutable artifacts produced by analysis pipeline steps.

    Invariants:
    - Must specify schema_version and producer_version.
    - Captures input_hash and input_artifact_ids for reproducibility and idempotency.
    """

    artifact_id: str = Field(min_length=1)
    analysis_id: str = Field(min_length=1)
    artifact_type: ArtifactType
    schema_version: str = "1.0"
    tenant_id: str = Field(min_length=1)
    pr_id: str = Field(min_length=1)
    input_artifact_ids: list[str] = Field(default_factory=list)
    input_hash: str = Field(min_length=1)
    producer: str = Field(min_length=1)
    producer_version: str = "1.0"
    created_at: UtcDateTime
    payload: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AnalysisArtifact",
    "ArtifactType",
]
