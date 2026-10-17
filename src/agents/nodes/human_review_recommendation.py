from __future__ import annotations

from typing import Literal, assert_never

from langgraph.types import interrupt

from src.agents.state import ProcurementAgentState
from src.domain.agent.approval import BuyerAction, BuyerSubmitApprovalRequest


class AnalysisRevisionMismatchError(ValueError):
    __slots__ = ("actual", "expected")

    expected: int
    actual: int

    def __init__(self, *, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"Expected analysis revision {self.expected}, received {self.actual}"


def human_review_recommendation(
    state: ProcurementAgentState,
) -> ProcurementAgentState:
    analysis_revision = state.get("analysis_revision", 1)
    response = interrupt(
        {
            "checkpoint": "recommendation_review",
            "analysis_revision": analysis_revision,
            "decision_proposal": state["decision_proposal"].model_dump(mode="json"),
            "comparison_matrix": state["comparison_matrix"].model_dump(mode="json"),
            "max_revise_reached": state.get("revise_count", 0) >= 3,
        }
    )
    request = BuyerSubmitApprovalRequest.model_validate(response)
    if request.analysis_revision != analysis_revision:
        raise AnalysisRevisionMismatchError(
            expected=analysis_revision,
            actual=request.analysis_revision,
        )
    return {"buyer_approval_request": request}


def buyer_decision_router(
    state: ProcurementAgentState,
) -> Literal["submit", "revise", "invalid"]:
    request = state.get("buyer_approval_request")
    if request is None:
        return "invalid"
    match request.action:
        case BuyerAction.SUBMIT:
            return "submit"
        case BuyerAction.REVISE:
            return "revise"
        case unreachable:
            assert_never(unreachable)
