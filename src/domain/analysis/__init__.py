"""Canonical deterministic and AI analysis artifacts."""

from src.domain.analysis.comparison import ComparisonCell, ComparisonMatrix
from src.domain.analysis.decision import DecisionProposal, Recommendation
from src.domain.analysis.normalization import NormalizedLine, NormalizedQuotation
from src.domain.analysis.risk import RiskFlag
from src.domain.analysis.tco import TCOItem, TCOResult

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
