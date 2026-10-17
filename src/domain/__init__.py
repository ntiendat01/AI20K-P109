"""Canonical Pydantic contracts for the procurement backend."""

from src.domain.analysis import ComparisonMatrix, DecisionProposal, NormalizedQuotation, RiskFlag, TCOResult
from src.domain.approval import ApprovalDecision, BuyerRecommendationConfirmation, ManagerDecisionRequest
from src.domain.document import DocumentRepresentation, UploadedDocument
from src.domain.fuzzy_match import BatchMatchResult, ConfirmMatchRequest, MatchCandidate, MatchResult, MatchStatus
from src.domain.purchase_order import PurchaseOrder
from src.domain.purchase_request import PurchaseRequest
from src.domain.quotation import ConfirmedQuotation, QuotationConfirmation, RawExtraction
from src.domain.workflow import Analysis, AnalysisArtifact, AnalysisResult, WorkflowJob

__all__ = [
    "Analysis",
    "AnalysisArtifact",
    "AnalysisResult",
    "ApprovalDecision",
    "BatchMatchResult",
    "BuyerRecommendationConfirmation",
    "ComparisonMatrix",
    "ConfirmMatchRequest",
    "ConfirmedQuotation",
    "DecisionProposal",
    "DocumentRepresentation",
    "ManagerDecisionRequest",
    "MatchCandidate",
    "MatchResult",
    "MatchStatus",
    "NormalizedQuotation",
    "PurchaseOrder",
    "PurchaseRequest",
    "QuotationConfirmation",
    "RawExtraction",
    "RiskFlag",
    "TCOResult",
    "UploadedDocument",
    "WorkflowJob",
]
