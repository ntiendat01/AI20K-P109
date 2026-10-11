from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Final
from uuid import NAMESPACE_URL, uuid5

from src.agents.state import ProcurementAgentState
from src.agents.tools.normalize_data import FX_RATES_TO_VND, UOM_CONVERSION_TABLE
from src.models_v1.analysis.normalization import (
    NormalizationStatus,
    NormalizedItem,
    NormalizedQuotationArtifact,
)
from src.models_v1.quotation.confirmation import QuotationConfirmationRequest

NORMALIZATION_RULE_VERSION: Final = "uom-fx-v1"
MONEY_QUANTUM: Final = Decimal("0.01")


def normalize(state: ProcurementAgentState) -> ProcurementAgentState:
    confirmed_quotes = state.get("confirmed_quotes", [])
    if not confirmed_quotes:
        return {"normalized_quotes": []}

    pr_data = state.get("pr_data", {})
    target_uom = str(pr_data.get("target_uom", "cái")).strip()
    target_currency = str(pr_data.get("target_currency", "VND")).strip().upper()
    preserve_line_item_uom = bool(pr_data.get("preserve_line_item_uom", False))
    rule_version = state.get("normalization_rule_version", NORMALIZATION_RULE_VERSION)

    artifacts = [
        _normalize_quote(
            quote,
            quotation_revision_id=_stable_revision_id(state.get("case_id", ""), index, quote),
            target_uom=target_uom,
            target_currency=target_currency,
            preserve_line_item_uom=preserve_line_item_uom,
            rule_version=rule_version,
        )
        for index, quote in enumerate(confirmed_quotes)
    ]
    return {"normalized_quotes": artifacts}


def _normalize_quote(
    quote: QuotationConfirmationRequest,
    *,
    quotation_revision_id: str,
    target_uom: str,
    target_currency: str,
    preserve_line_item_uom: bool,
    rule_version: str,
) -> NormalizedQuotationArtifact:
    normalized_items: list[NormalizedItem] = []
    issues: list[str] = []

    for index, item in enumerate(quote.items):
        item_target_uom = item.unit if preserve_line_item_uom else target_uom
        uom_factor = _uom_factor(item.unit, item_target_uom)
        fx_rate = _currency_rate(quote.currency, target_currency)
        item_issues: list[str] = []
        if uom_factor is None:
            item_issues.append(f"items[{index}]: missing UOM mapping '{item.unit}' -> '{item_target_uom}'")
        if fx_rate is None:
            item_issues.append(f"items[{index}]: missing FX rate '{quote.currency.upper()}' -> '{target_currency}'")
        issues.extend(item_issues)

        if item_issues:
            normalized_items.append(
                NormalizedItem(
                    source_quantity=item.quantity,
                    source_uom=item.unit,
                    source_unit_price=item.unit_price,
                    source_currency=quote.currency,
                )
            )
            continue

        assert uom_factor is not None
        assert fx_rate is not None
        normalized_items.append(
            NormalizedItem(
                source_quantity=item.quantity,
                source_uom=item.unit,
                source_unit_price=item.unit_price,
                source_currency=quote.currency,
                normalized_quantity=item.quantity * uom_factor,
                normalized_uom=item_target_uom,
                normalized_unit_price=(item.unit_price / uom_factor * fx_rate).quantize(
                    MONEY_QUANTUM,
                    rounding=ROUND_HALF_UP,
                ),
                normalized_currency=target_currency,
                rule_id=_rule_id(item.unit, item_target_uom, quote.currency, target_currency),
            )
        )

    return NormalizedQuotationArtifact(
        quotation_revision_id=quotation_revision_id,
        rule_version=rule_version,
        status=NormalizationStatus.NEEDS_MAPPING if issues else NormalizationStatus.NORMALIZED,
        items=normalized_items,
        issues=issues,
    )


def _uom_factor(source_uom: str, target_uom: str) -> Decimal | None:
    source_key = source_uom.casefold().strip()
    target_key = target_uom.casefold().strip()
    if source_key == target_key:
        return Decimal(1)

    source = UOM_CONVERSION_TABLE.get(source_key)
    target = UOM_CONVERSION_TABLE.get(target_key)
    if source is None or target is None or source[0] != target[0]:
        return None
    return Decimal(str(source[1])) / Decimal(str(target[1]))


def _currency_rate(source_currency: str, target_currency: str) -> Decimal | None:
    source_key = source_currency.upper().strip()
    target_key = target_currency.upper().strip()
    if source_key == target_key:
        return Decimal(1)

    source_rate = FX_RATES_TO_VND.get(source_key)
    target_rate = FX_RATES_TO_VND.get(target_key)
    if source_rate is None or target_rate is None:
        return None
    return Decimal(str(source_rate)) / Decimal(str(target_rate))


def _rule_id(source_uom: str, target_uom: str, source_currency: str, target_currency: str) -> str:
    return (
        f"uom:{source_uom.casefold().strip()}->{target_uom.casefold().strip()};"
        f"fx:{source_currency.upper().strip()}->{target_currency.upper().strip()}"
    )


def _stable_revision_id(case_id: str, index: int, quote: QuotationConfirmationRequest) -> str:
    identity = f"{case_id}#{index}#{quote.model_dump_json()}"
    return str(uuid5(NAMESPACE_URL, identity))
