"""Schemas for fuzzy product matching between QuoteItems and PR items.

Pipeline: Normalization → Scoring → Decision → Storage.
Implements Heuristic + Trigram approach (Phương án 3) as decided in
fuzzy-matching-architecture.md.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from src.models.common import ContractModel


class MatchStatus(StrEnum):
    """Track matching lifecycle for a single QuoteItem against a PR item."""

    UNMATCHED = "unmatched"
    AUTO_MATCHED = "auto_matched"  # score >= 0.90
    SUGGESTED = "suggested"  # 0.70 <= score < 0.90
    MANUAL_MATCHED = "manual_matched"  # confirmed by Buyer
    REJECTED = "rejected"  # Buyer explicitly rejected suggestion


class MatchAction(StrEnum):
    """Buyer action when reviewing a SUGGESTED match."""

    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    MAP_TO_NEW = "MAP_TO_NEW"


class ItemNormalized(ContractModel):
    """Carry the normalized form of an item name used for scoring.

    Normalization steps applied:
    1. Lowercase + strip whitespace.
    2. Remove Vietnamese diacritics.
    3. Remove stop-words ('cái', 'chiếc', 'loại', 'hàng').
    4. Apply synonym dictionary (e.g. 'inox' → 'thep khong gi').
    """

    original: str
    normalized: str


class MatchCandidate(ContractModel):
    """Represent one candidate PR item scored against a QuoteItem."""

    pr_item_id: str = Field(min_length=1)
    pr_item_name: str
    score: float = Field(ge=0.0, le=1.0, description="Composite similarity score (0–1)")
    name_score: float = Field(ge=0.0, le=1.0, description="Name similarity sub-score (weight 0.60)")
    uom_score: float = Field(ge=0.0, le=1.0, description="UoM similarity sub-score (weight 0.20)")
    attr_score: float = Field(ge=0.0, le=1.0, description="Attribute similarity sub-score (weight 0.20)")
    status: MatchStatus


class MatchResult(ContractModel):
    """Report matching outcome for a single QuoteItem.

    If ``best_match`` is None the item has no viable candidate for review.
    Candidates below the suggested threshold may be returned with
    ``UNMATCHED`` status so the Buyer can map them manually.
    """

    quote_item_id: str = Field(min_length=1)
    quote_item_name: str
    best_match: MatchCandidate | None = None
    candidates: list[MatchCandidate] = Field(default_factory=list)
    normalized_name: str = ""


class BatchMatchResult(ContractModel):
    """Aggregate fuzzy-matching results for all items in one quotation pass."""

    total: int = Field(ge=0)
    auto_matched: int = Field(ge=0)
    suggested: int = Field(ge=0)
    unmatched: int = Field(ge=0)
    results: list[MatchResult] = Field(default_factory=list)


class ConfirmMatchRequest(ContractModel):
    """Payload for ``POST /api/quotes/{quote_id}/items/{item_id}/confirm-match``.

    Sent by the Buyer when manually reviewing SUGGESTED matches.
    """

    pr_item_id: str | None = Field(
        default=None, description="Target PR item to map to (required for CONFIRM/MAP_TO_NEW)"
    )
    action: MatchAction


class SynonymEntry(ContractModel):
    """Persist a confirmed (original_name, pr_item_id) pair for exact-match reuse."""

    original_name: str = Field(min_length=1)
    pr_item_id: str = Field(min_length=1)
    learned_from_case: str | None = None


__all__ = [
    "BatchMatchResult",
    "ConfirmMatchRequest",
    "ItemNormalized",
    "MatchAction",
    "MatchCandidate",
    "MatchResult",
    "MatchStatus",
    "SynonymEntry",
]
