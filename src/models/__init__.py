"""Canonical Pydantic contracts for the procurement backend."""

from src.models.analysis import ComparisonMatrix, DecisionProposal, NormalizedQuotation, RiskFlag, TCOResult
from src.models.approval import ApprovalDecision, BuyerRecommendationConfirmation, ManagerDecisionRequest
from src.models.document import DocumentRepresentation, UploadedDocument
from src.models.fuzzy_match import BatchMatchResult, MatchCandidate, MatchResult, MatchStatus, ConfirmMatchRequest
from src.models.purchase_order import PurchaseOrder
from src.models.purchase_request import PurchaseRequest
from src.models.quotation import ConfirmedQuotation, QuotationConfirmation, RawExtraction
from src.models.workflow import Analysis, AnalysisArtifact, AnalysisResult, WorkflowJob

__all__ = [
    "Analysis",
    "AnalysisArtifact",
    "AnalysisResult",
    "ApprovalDecision",
    "BatchMatchResult",
    "BuyerRecommendationConfirmation",
    "ComparisonMatrix",
    "ConfirmedQuotation",
    "DecisionProposal",
    "DocumentRepresentation",
    "ManagerDecisionRequest",
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
