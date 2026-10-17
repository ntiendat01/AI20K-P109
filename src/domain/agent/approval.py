"""Buyer HITL-2 recommendation review and Manager approval decision models for agent contract models."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from src.domain.agent.common import ContractModel, UtcDateTime


class BuyerAction(StrEnum):
    """Action taken by the Buyer upon reviewing the AI recommendation."""

    SUBMIT = "submit"
    REVISE = "revise"


class ManagerDecision(StrEnum):
    """Decision taken by the Manager upon reviewing submitted analysis."""

    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"


class BuyerSubmitApprovalRequest(ContractModel):
    """Command payload sent by Buyer to submit or request revision of an analysis."""

    analysis_revision: int = Field(ge=1)
    action: BuyerAction
    note: str | None = None

    @model_validator(mode="after")
    def validate_revise_note(self) -> "BuyerSubmitApprovalRequest":
        if self.action == BuyerAction.REVISE and not self.note:
            raise ValueError("note is required when Buyer requests revision")
        return self


class BuyerRecommendationConfirmation(ContractModel):
    """Immutable record of the Buyer's review and approval submission."""

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    pr_id: str = Field(min_length=1)
    analysis_id: str = Field(min_length=1)
    analysis_revision: int = Field(ge=1)
    decision_proposal_artifact_id: str = Field(min_length=1)
    action: BuyerAction
    note: str | None = None
    buyer_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    created_at: UtcDateTime


class BuyerSubmitApprovalResponse(ContractModel):
    """Response returned upon successful Buyer submit approval (200 OK)."""

    confirmation_id: str
    analysis_id: str
    analysis_revision: int = Field(ge=1)
    status: Literal["pending_manager_approval"] = "pending_manager_approval"
    submitted_by: str
    submitted_at: UtcDateTime


class ManagerDecisionRequest(ContractModel):
    """Command payload sent by Manager to make a decision on submitted analysis."""

    analysis_revision: int = Field(ge=1)
    decision: ManagerDecision
    selected_supplier_id: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_decision_rules(self) -> "ManagerDecisionRequest":
        if self.decision == ManagerDecision.APPROVE and not self.selected_supplier_id:
            raise ValueError("selected_supplier_id is required when approving")
        if self.decision in {ManagerDecision.REVISE, ManagerDecision.REJECT} and not self.reason:
            raise ValueError("reason is required when revising or rejecting")
        return self


class ApprovalDecision(ContractModel):
    """Immutable record of the Manager's approval decision."""

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    pr_id: str = Field(min_length=1)
    analysis_id: str = Field(min_length=1)
    analysis_revision: int = Field(ge=1)
    buyer_confirmation_id: str = Field(min_length=1)
    decision: ManagerDecision
    selected_supplier_id: str | None = None
    reason: str | None = None
    actor_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    created_at: UtcDateTime


class ManagerDecisionResponse(ContractModel):
    """Response returned upon Manager decision execution."""

    decision_id: str
    status: Literal["approved", "revised", "rejected"]
    purchase_order_id: str | None = None


__all__ = [
    "ApprovalDecision",
    "BuyerAction",
    "BuyerRecommendationConfirmation",
    "BuyerSubmitApprovalRequest",
    "BuyerSubmitApprovalResponse",
    "ManagerDecision",
    "ManagerDecisionRequest",
    "ManagerDecisionResponse",
]
