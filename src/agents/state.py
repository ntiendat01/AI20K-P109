from __future__ import annotations

from typing import Literal, TypedDict

from src.domain.agent.analysis.comparison import SupplierComparisonMatrix
from src.domain.agent.analysis.decision import DecisionProposal
from src.domain.agent.analysis.normalization import NormalizedQuotationArtifact
from src.domain.agent.analysis.risk import RiskFlag
from src.domain.agent.analysis.tco import TCOResult
from src.domain.agent.approval import BuyerSubmitApprovalRequest
from src.domain.agent.quotation.confirmation import QuotationConfirmationRequest
from src.domain.agent.quotation.extraction import ValidatedExtraction


class ProcurementAgentState(TypedDict, total=False):
    """Serializable values passed between procurement workflow nodes."""

    case_id: str
    pr_data: dict[str, object]
    documents: list[str]
    raw_extractions: list[dict[str, object]]
    validated_extractions: list[ValidatedExtraction]
    confirmed_quotes: list[QuotationConfirmationRequest]
    # Supplier IDs remain server-owned.  The confirmation contract intentionally
    # contains only buyer-editable values, so keep the parallel identity mapping
    # in the server-side graph state.
    confirmed_supplier_ids: list[str]
    review_mode: Literal["mandatory", "optional"]
    normalization_rule_version: str
    normalized_quotes: list[NormalizedQuotationArtifact]
    fuzzy_match_results: dict[str, object]
    tco_results: list[TCOResult]
    comparison_matrix: SupplierComparisonMatrix
    risk_flags: list[RiskFlag]
    analysis_revision: int
    buyer_approval_request: BuyerSubmitApprovalRequest

    recommendation: dict[str, object]
    human_feedback: dict[str, object]
    revise_count: int
    decision_proposal: DecisionProposal
    evaluation_result: dict[str, object]
    workflow_status: str
    message: str
    decision_retry_count: int
    decision_observability: dict[str, object]
    recommendation_id: str
    recommendation_version: int

    analysis_id: str

    decision_context: dict[str, object]

    require_explicit_confirmation: bool
