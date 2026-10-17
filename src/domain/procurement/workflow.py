"""Public integration contracts; policy and source snapshots remain server-owned."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domain.analysis.evaluation import EvaluationResult, Feedback, FeedbackReceipt
from src.domain.procurement.contracts import PurchaseOrder
from src.domain.procurement.pipeline import ComparisonMatrix, RiskFlag, TCOResult
from src.domain.purchase_request import PurchaseRequest

WorkflowStatus = Literal[
    "not_started",
    "running",
    "stale",
    "awaiting_buyer_review",
    "pending_manager_approval",
    "needs_input",
    "repairable",
    "technical_failure",
    "exception_required",
    "no_viable_supplier",
    "approved",
    "rejected",
    "closed",
    "awaiting_input",
    "awaiting_repair",
]


class AnalysisEvent(BaseModel):
    node: str
    at: datetime


class ProcurementAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pr_id: str
    status: WorkflowStatus
    analysis_id: str | None = None
    recommendation_id: str | None = None
    recommendation_version: int | None = None
    snapshot_revision: str | None = None
    message: str | None = None
    manager_note: str | None = None
    events: list[AnalysisEvent] = Field(default_factory=list)
    supplier_names: dict[str, str] = Field(default_factory=dict)
    tco_results: list[TCOResult] = Field(default_factory=list)
    comparison_matrix: ComparisonMatrix = Field(default_factory=ComparisonMatrix)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    # Temporary bypass: expose the Decision LLM payload while evaluation is disabled.
    decision_proposal: dict[str, JsonValue] = Field(default_factory=dict)
    evaluation: EvaluationResult | None = None
    review: dict[str, JsonValue] | None = None
    pending_feedback: Feedback | None = None
    applied_feedback_id: str | None = None
    missing_fields: list[dict[str, JsonValue]] = Field(default_factory=list)
    pr: PurchaseRequest | None = None


class ProcurementFeedbackResult(BaseModel):
    receipt: FeedbackReceipt
    status: WorkflowStatus
    po: PurchaseOrder | None = None
