from __future__ import annotations

import re
from collections.abc import Mapping

from src.agents.state import ProcurementAgentState
from src.models.procurement import EvidenceItem as EvidenceItemModel
from src.models.procurement import Recommendation as RecommendationModel

FIELD_PATTERNS = {
    "lead_time": re.compile(r"\b(?:lead[ _-]?time|delivery|giao)\b", re.IGNORECASE),
    "warranty": re.compile(r"\b(?:warranty|bảo hành)\b", re.IGNORECASE),
    "unit_price": re.compile(r"\b(?:unit[ _-]?price|price|đơn giá|giá)\b", re.IGNORECASE),
    "tco": re.compile(r"\b(?:tco|total cost|tổng chi phí)\b", re.IGNORECASE),
}


def generate_evidence(state: ProcurementAgentState) -> ProcurementAgentState:
    """Attach PDF citations to each ranked supplier without changing analysis data."""
    current = state.get("recommendation", {})
    enriched: list[dict[str, object]] = []
    ranked_value = current.get("ranked")
    ranked = ranked_value if isinstance(ranked_value, list) else []
    for item in ranked:
        if not isinstance(item, dict):
            continue
        supplier_id = item.get("supplier_id", item.get("supplier"))
        if not isinstance(supplier_id, str):
            continue
        rank = item.get("rank")
        rationale = item.get("rationale")
        if not isinstance(rank, int) or not isinstance(rationale, str):
            continue
        ranked_item: dict[str, object] = {
            "rank": rank,
            "supplier_id": supplier_id,
            "rationale": rationale,
            "evidence": _evidence_for(item, state),
        }
        enriched.append(ranked_item)

    recommendation = RecommendationModel.model_validate({**dict(current), "ranked": enriched}).model_dump(mode="json")
    return {"recommendation": recommendation}


def _evidence_for(item: dict[str, object], state: ProcurementAgentState) -> list[dict[str, object]]:
    supplier = item.get("supplier_id", item.get("supplier"))
    if not isinstance(supplier, str):
        return []
    rationale = item.get("rationale")
    if not isinstance(rationale, str):
        return [_missing_evidence("unknown", supplier)]
    fields = [field for field, pattern in FIELD_PATTERNS.items() if pattern.search(rationale)]
    if not fields:
        return [_missing_evidence("unknown", supplier)]
    return [_evidence_item(field, supplier, state) for field in fields]


def _evidence_item(
    field: str,
    supplier: str,
    state: ProcurementAgentState,
) -> dict[str, object]:
    raw = _quote_for_supplier(state.get("raw_extractions", []), supplier)
    normalized_quote = _quote_for_supplier(state.get("normalized_quotes", []), supplier)
    normalized = _normalized_line(normalized_quote, raw)
    source_field = {"lead_time": "lead_time_days", "warranty": "warranty_months"}.get(field, field)
    if field == "tco":
        source_field = "unit_price"

    if raw is None:
        return _missing_evidence(field, supplier)

    source_ref = raw.get("source")
    if isinstance(source_ref, Mapping):
        source = dict(source_ref)
    else:
        source = {
            "document_path": raw.get("document"),
            "page_number": raw.get("page_number"),
        }
    has_source = any(value is not None for value in source.values())
    evidence: dict[str, object] = {
        "field": field,
        "supplier_id": supplier,
        "source": source if has_source else None,
    }
    if (
        not has_source
        or not isinstance(source.get("page_number"), int)
        or not isinstance(source.get("document_path"), str)
    ):
        evidence["low_confidence"] = True

    original = raw.get(source_field)
    current = normalized.get(source_field) if normalized is not None else original
    if normalized is not None and normalized.get("confirmed_by_human") is True and current != original:
        evidence["edited_by_human"] = True
        evidence["original_value"] = original
    return EvidenceItemModel.model_validate(evidence).model_dump(mode="json")


def _quote_for_supplier(quotes: object, supplier: str) -> Mapping[str, object] | None:
    if not isinstance(quotes, list):
        return None
    for quote in quotes:
        if isinstance(quote, Mapping) and quote.get("supplier_id", quote.get("supplier")) == supplier:
            return quote
    return None


def _normalized_line(
    quote: Mapping[str, object] | None,
    raw: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    """Find the normalized line corresponding to a canonical raw extraction."""
    if quote is None:
        return None
    items = quote.get("items")
    if not isinstance(items, list):
        return quote

    extraction_id = raw.get("extraction_id") if raw is not None else None
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if extraction_id is not None and item.get("extraction_id") == extraction_id:
            return item
    return next((item for item in items if isinstance(item, Mapping)), None)


def _missing_evidence(field: str, supplier: str) -> dict[str, object]:
    return {
        "field": field,
        "supplier_id": supplier,
        "source": None,
        "low_confidence": True,
    }
