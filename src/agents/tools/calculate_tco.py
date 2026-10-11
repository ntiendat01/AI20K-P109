from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from src.models_v1.analysis.normalization import NormalizedQuotationArtifact
from src.models_v1.analysis.tco import (
    TCOBreakdownItem,
    TCOCalculationStatus,
    TCOResult,
)
from src.models_v1.quotation.confirmation import QuotationConfirmationRequest

MONEY_QUANTUM: Final = Decimal("0.01")
ZERO_MONEY: Final = Decimal("0.00")


def calculate_tco(
    normalized_quotes: list[NormalizedQuotationArtifact],
    confirmed_quotes: list[QuotationConfirmationRequest],
    target_currency: str,
    *,
    supplier_ids: list[str] | None = None,
) -> list[TCOResult]:
    results: list[TCOResult] = []
    for quote_index, (normalized, confirmed) in enumerate(zip(normalized_quotes, confirmed_quotes, strict=True)):
        subtotal = ZERO_MONEY
        total_vat = ZERO_MONEY
        breakdown: list[TCOBreakdownItem] = []
        missing_fields: list[str] = []
        vat_rate = Decimal(0) if confirmed.vat_included else confirmed.vat_rate

        for item_index, (normalized_item, confirmed_item) in enumerate(
            zip(normalized.items, confirmed.items, strict=True)
        ):
            if normalized_item.normalized_quantity is None:
                missing_fields.append(f"items[{item_index}].normalized_quantity")
            if normalized_item.normalized_unit_price is None:
                missing_fields.append(f"items[{item_index}].normalized_unit_price")
            if normalized_item.normalized_quantity is None or normalized_item.normalized_unit_price is None:
                continue

            item_subtotal = _money(normalized_item.normalized_quantity * normalized_item.normalized_unit_price)
            vat_amount = _money(item_subtotal * vat_rate)
            item_tco = _money(item_subtotal + vat_amount)
            subtotal = _money(subtotal + item_subtotal)
            total_vat = _money(total_vat + vat_amount)
            breakdown.append(
                TCOBreakdownItem(
                    item_name=confirmed_item.product_name,
                    quantity=normalized_item.normalized_quantity,
                    unit_price=normalized_item.normalized_unit_price,
                    subtotal=item_subtotal,
                    surcharges=ZERO_MONEY,
                    vat_rate=vat_rate,
                    vat_amount=vat_amount,
                    item_tco=item_tco,
                )
            )

        status = TCOCalculationStatus.MISSING_DATA if missing_fields else TCOCalculationStatus.CALCULATED
        results.append(
            TCOResult(
                supplier_id=_supplier_id(confirmed, supplier_ids, quote_index),
                quotation_revision_id=normalized.quotation_revision_id,
                currency=target_currency.upper(),
                subtotal=subtotal,
                total_surcharges=ZERO_MONEY,
                total_vat=total_vat,
                total_tco=None if missing_fields else _money(subtotal + total_vat),
                status=status,
                missing_fields=missing_fields,
                breakdown=breakdown,
            )
        )
    return results


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _supplier_id(confirmed: QuotationConfirmationRequest, supplier_ids: list[str] | None, index: int) -> str:
    """Use the server-owned ID when the workflow supplied one.

    Standalone node tests and the document-only graph deliberately remain
    usable without it, where supplier_name is the only available identity.
    """
    if supplier_ids is not None and index < len(supplier_ids) and supplier_ids[index]:
        return supplier_ids[index]
    return confirmed.supplier_name
