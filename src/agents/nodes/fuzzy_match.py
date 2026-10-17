"""Agent node: run fuzzy matching after quote normalization.

Invoked in the procurement graph after ``normalize`` to detect which
extracted QuoteItems map to the same PR item.  Updates state with
``fuzzy_match_results`` for downstream display and Buyer review.
"""

from __future__ import annotations

from src.agents.state import ProcurementAgentState
from src.domain.fuzzy_match import BatchMatchResult
from src.domain.matching import (
    PRItem,
    ProductMatchingService,
    QuoteItemInput,
)


def fuzzy_match(state: ProcurementAgentState) -> ProcurementAgentState:
    """Run ProductMatchingService against confirmed/normalized quote items.

    Reads from state:
    - ``confirmed_quotes``: list of QuotationConfirmationRequest, each with
      ``.items`` (product_name, unit, …).
    - ``pr_data``: must contain ``"items"`` — list of dicts with keys
      ``id``, ``name``, ``uom``, ``description`` (optional).

    Writes to state:
    - ``fuzzy_match_results``: ``BatchMatchResult`` as a JSON-serialisable dict.
    """
    confirmed_quotes = state.get("confirmed_quotes", [])
    pr_data = state.get("pr_data", {})
    raw_pr_items: list[dict] = pr_data.get("items", []) if isinstance(pr_data, dict) else []

    # Build PR item list
    pr_items: list[PRItem] = [
        PRItem(
            id=str(r.get("id", f"pr_{i}")),
            name=str(r.get("name", r.get("category", ""))),
            uom=r.get("uom") or r.get("requested_uom"),
            description=r.get("description"),
        )
        for i, r in enumerate(raw_pr_items)
    ]

    # When PR has no structured item list, fall back to single-item from category
    if not pr_items:
        category = pr_data.get("category") if isinstance(pr_data, dict) else None
        if category:
            pr_items = [
                PRItem(
                    id="pr_main",
                    name=str(category),
                    uom=pr_data.get("requested_uom") if isinstance(pr_data, dict) else None,
                )
            ]

    # Build QuoteItem list from all confirmed quotes
    quote_items: list[QuoteItemInput] = []
    for q_idx, quote in enumerate(confirmed_quotes):
        items = getattr(quote, "items", [])
        for i_idx, item in enumerate(items):
            name = getattr(item, "product_name", None) or getattr(item, "item_name", "")
            unit = getattr(item, "unit", None)
            quote_items.append(
                QuoteItemInput(
                    id=f"q{q_idx}_i{i_idx}",
                    name=str(name),
                    uom=unit,
                )
            )

    if not quote_items or not pr_items:
        empty = BatchMatchResult(total=0, auto_matched=0, suggested=0, unmatched=0)
        return {"fuzzy_match_results": empty.model_dump(mode="json")}

    service = ProductMatchingService()
    batch: BatchMatchResult = service.match(quote_items, pr_items)
    return {"fuzzy_match_results": batch.model_dump(mode="json")}
