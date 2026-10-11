"""Schemas for Buyer recommendation review and Manager approval decisions."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from src.models.common import ContractModel


class BuyerRecommendationSubmission(ContractModel):
    """Validate a Buyer action taken after reviewing an AI recommendation."""

    analysis_revision: int = Field(ge=1)
    action: Literal["submit", "revise"]
    note: str | None = None

    @model_validator(mode="after")
    def require_revision_note(self) -> "BuyerRecommendationSubmission":
        if self.action == "revise" and not self.note:
            raise ValueError("note is required when Buyer requests revision")
        return self


class BuyerRecommendationConfirmation(ContractModel):
    """Record the immutable Buyer confirmation that authorizes Manager review."""

    confirmation_id: str
    analysis_id: str
    analysis_revision: int = Field(ge=1)
    decision_proposal_artifact_id: str
    action: Literal["submit", "revise"]
    note: str | None = None
    buyer_id: str
    submitted_at: datetime


class ManagerDecisionRequest(ContractModel):
    """Validate a Manager approve, revise, or reject command for a reviewed analysis."""

    analysis_revision: int = Field(ge=1)
    decision: Literal["approve", "revise", "reject"]
    selected_supplier_id: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_decision_fields(self) -> "ManagerDecisionRequest":
        if self.decision == "approve" and not self.selected_supplier_id:
            raise ValueError("selected_supplier_id is required when approving")
        if self.decision in {"revise", "reject"} and not self.reason:
            raise ValueError("reason is required when revising or rejecting")
        return self


class ApprovalDecision(ContractModel):
    """Record the immutable Manager decision linked to Buyer confirmation."""

    decision_id: str
    analysis_id: str
    analysis_revision: int = Field(ge=1)
    buyer_confirmation_id: str
    decision: Literal["approve", "revise", "reject"]
    selected_supplier_id: str | None = None
    reason: str | None = None
    actor_id: str
    created_at: datetime
