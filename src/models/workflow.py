"""Schemas for analysis lifecycle, artifacts, and asynchronous workflow jobs."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from src.models.analysis import ComparisonMatrix, RiskFlag, TCOResult
from src.models.analysis.decision import DecisionProposal
from src.models.common import ContractModel

AnalysisStatus = Literal[
    "queued",
    "running",
    "awaiting_buyer_review",
    "pending_manager_approval",
    "needs_input",
    "approved",
    "rejected",
    "failed",
    "superseded",
]


class AnalysisInput(ContractModel):
    """Pin one immutable confirmed quotation revision into an analysis snapshot."""

    quotation_revision_id: str
    content_hash: str


class AnalysisArtifact(ContractModel):
    """Envelope one immutable output produced by a versioned analysis component."""

    artifact_id: str
    analysis_id: str
    artifact_type: Literal["normalization", "tco", "risk", "comparison", "decision"]
    schema_version: str
    producer: str
    producer_version: str
    input_artifact_ids: list[str] = Field(default_factory=list)
    input_hash: str
    payload: dict[str, Any]
    created_at: datetime


class Analysis(ContractModel):
    """Represent one versioned analysis run over an immutable input snapshot."""

    analysis_id: str
    tenant_id: str
    pr_id: str
    revision_no: int = Field(ge=1)
    snapshot_hash: str
    status: AnalysisStatus
    recommendation_id: str | None = None
    inputs: list[AnalysisInput] = Field(default_factory=list)
    created_by: str
    created_at: datetime
    completed_at: datetime | None = None


class AnalysisResult(ContractModel):
    """Return the current analysis state and artifacts required by Buyer HITL."""

    analysis_id: str
    pr_id: str
    revision_no: int = Field(ge=1)
    snapshot_hash: str
    status: AnalysisStatus
    tco_results: list[TCOResult] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    comparison: ComparisonMatrix | None = None
    decision_proposal: DecisionProposal | None = None


class WorkflowJob(ContractModel):
    """Expose progress and failure information for one long-running workflow invocation."""

    job_id: str
    job_type: Literal["document_extraction", "procurement_analysis"]
    status: Literal["queued", "running", "waiting_for_human", "completed", "failed"]
    current_step: str
    progress: int = Field(ge=0, le=100)
    resource_id: str | None = None
    error: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowJobEvent(ContractModel):
    """Record one observable node transition for audit and progress reporting."""

    event_id: str
    job_id: str
    node: str
    status: Literal["started", "completed", "failed"]
    attempt: int = Field(ge=1)
    error: dict[str, Any] | None = None
    created_at: datetime
