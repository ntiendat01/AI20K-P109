"""Workflow jobs, events, and procurement analysis lifecycle models for agent contract models."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from src.domain.agent.analysis.comparison import SupplierComparisonMatrix
from src.domain.agent.analysis.decision import DecisionProposal
from src.domain.agent.analysis.risk import RiskFlag
from src.domain.agent.analysis.tco import TCOResult
from src.domain.agent.common import ContractModel, UtcDateTime


class AnalysisStatus(StrEnum):
    """Lifecycle status of a procurement analysis run."""

    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_BUYER_REVIEW = "awaiting_buyer_review"
    PENDING_MANAGER_APPROVAL = "pending_manager_approval"
    NEEDS_INPUT = "needs_input"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class JobType(StrEnum):
    """Types of long-running workflow jobs."""

    DOCUMENT_EXTRACTION = "document_extraction"
    PROCUREMENT_ANALYSIS = "procurement_analysis"


class JobStatus(StrEnum):
    """Execution status of an asynchronous workflow job."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_HUMAN = "waiting_for_human"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStep(StrEnum):
    """Steps executed within procurement workflows."""

    INTAKE = "intake"
    OCR = "ocr"
    EXTRACTION = "extraction"
    VALIDATION = "validation"
    WAITING_FOR_HUMAN = "waiting_for_human"
    NORMALIZATION = "normalization"
    TCO = "tco"
    RISK = "risk"
    COMPARISON = "comparison"
    DECISION = "decision"


class NodeEventStatus(StrEnum):
    """Status recorded for an individual node transition event."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisInput(ContractModel):
    """Immutable input pointer binding a confirmed quotation revision into an analysis snapshot."""

    analysis_id: str = Field(min_length=1)
    quotation_revision_id: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)


class Analysis(ContractModel):
    """Analysis aggregate entity representing one immutable execution over confirmed quotations."""

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    pr_id: str = Field(min_length=1)
    revision_no: int = Field(default=1, ge=1)
    snapshot_hash: str = Field(min_length=1)
    status: AnalysisStatus = AnalysisStatus.QUEUED
    recommendation_id: str | None = None
    created_by: str = Field(min_length=1)
    created_at: UtcDateTime
    completed_at: UtcDateTime | None = None


class AnalysisCreateResponse(ContractModel):
    """Response returned upon initiating a new analysis (POST /prs/{pr_id}/analyses - 202 Accepted)."""

    analysis_id: str
    analysis_revision: int = 1
    snapshot_hash: str
    job_id: str
    status: Literal["queued"] = "queued"


class AnalysisDetailResponse(ContractModel):
    """Response returned when querying an analysis (GET /analyses/{analysis_id})."""

    analysis_id: str
    pr_id: str
    analysis_revision: int = Field(ge=1)
    snapshot_hash: str
    status: AnalysisStatus
    quotation_revision_ids: list[str] = Field(default_factory=list)
    tco_results: list[TCOResult] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    comparison_matrix: SupplierComparisonMatrix | None = None
    decision_proposal: DecisionProposal | None = None
    created_at: UtcDateTime
    completed_at: UtcDateTime | None = None


class WorkflowJob(ContractModel):
    """WorkflowJob aggregate entity tracking asynchronous execution progress."""

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    pr_id: str = Field(min_length=1)
    job_type: JobType
    status: JobStatus = JobStatus.QUEUED
    current_step: WorkflowStep
    progress: int = Field(default=0, ge=0, le=100)
    resource_id: str | None = None
    error_json: dict[str, Any] | None = None
    idempotency_key: str | None = None
    input_hash: str | None = None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class WorkflowJobResponse(ContractModel):
    """Response returned when polling job status (GET /jobs/{job_id})."""

    job_id: str
    job_type: JobType
    status: JobStatus
    current_step: WorkflowStep
    progress: int = Field(ge=0, le=100)
    resource_id: str | None = None
    error: dict[str, Any] | None = None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class WorkflowJobEvent(ContractModel):
    """Auditable log event recording individual node execution status."""

    id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    node: str = Field(min_length=1)
    status: NodeEventStatus
    attempt: int = Field(default=1, ge=1)
    error_json: dict[str, Any] | None = None
    created_at: UtcDateTime


__all__ = [
    "Analysis",
    "AnalysisCreateResponse",
    "AnalysisDetailResponse",
    "AnalysisInput",
    "AnalysisStatus",
    "JobStatus",
    "JobType",
    "NodeEventStatus",
    "WorkflowJob",
    "WorkflowJobEvent",
    "WorkflowJobResponse",
    "WorkflowStep",
]
