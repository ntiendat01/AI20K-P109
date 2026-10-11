"""Canonical deterministic and AI analysis artifacts."""

from src.models.analysis.comparison import ComparisonCell, ComparisonMatrix
from src.models.analysis.decision import DecisionProposal, Recommendation
from src.models.analysis.normalization import NormalizedLine, NormalizedQuotation
from src.models.analysis.risk import RiskFlag
from src.models.analysis.tco import TCOItem, TCOResult

__all__ = [
    "ComparisonCell",
    "ComparisonMatrix",
    "DecisionProposal",
    "NormalizedLine",
    "NormalizedQuotation",
    "Recommendation",
    "RiskFlag",
    "TCOItem",
    "TCOResult",
]
