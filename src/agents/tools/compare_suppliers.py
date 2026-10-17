from __future__ import annotations

from decimal import Decimal
from typing import Final

from src.domain.agent.analysis.comparison import ComparisonCell, SupplierComparisonMatrix
from src.domain.agent.analysis.normalization import NormalizedQuotationArtifact
from src.domain.agent.analysis.tco import TCOResult
from src.domain.agent.quotation.confirmation import QuotationConfirmationRequest
from src.infrastructure.repositories.system_settings import get_dynamic_settings

CRITERIA: Final = ("total_tco", "lead_time_days", "warranty_months")
DEFAULT_DEVIATION_THRESHOLD: Final = Decimal("0.15")
MISSING_DATA: Final = "Thiếu dữ liệu"
INSUFFICIENT_DATA: Final = "Không đủ dữ liệu so sánh"


def compare_suppliers(
    normalized_quotes: list[NormalizedQuotationArtifact],
    confirmed_quotes: list[QuotationConfirmationRequest],
    tco_results: list[TCOResult],
    *,
    supplier_ids: list[str] | None = None,
    deviation_threshold: Decimal | None = None,
) -> SupplierComparisonMatrix:
    threshold = (
        deviation_threshold
        if deviation_threshold is not None
        else Decimal(str(get_dynamic_settings().deviation_threshold))
    )
    tco_by_revision = {result.quotation_revision_id: result for result in tco_results}
    supplier_values: dict[str, dict[str, Decimal | None]] = {}

    for index, (normalized, confirmed) in enumerate(zip(normalized_quotes, confirmed_quotes, strict=True)):
        tco = tco_by_revision.get(normalized.quotation_revision_id)
        supplier_id = tco.supplier_id if tco is not None else _supplier_id(confirmed.supplier_name, supplier_ids, index)
        supplier_values[supplier_id] = {
            "total_tco": tco.total_tco if tco is not None else None,
            "lead_time_days": Decimal(confirmed.lead_time_days),
            "warranty_months": Decimal(confirmed.warranty_months),
        }

    means = {
        criterion: _mean([values[criterion] for values in supplier_values.values() if values[criterion] is not None])
        for criterion in CRITERIA
    }
    matrix: dict[str, dict[str, ComparisonCell]] = {}
    for supplier_id, values in supplier_values.items():
        matrix[supplier_id] = {
            criterion: _cell(
                value=values[criterion],
                mean=means[criterion],
                comparable_count=sum(candidate[criterion] is not None for candidate in supplier_values.values()),
                deviation_threshold=threshold,
            )
            for criterion in CRITERIA
        }

    return SupplierComparisonMatrix(
        suppliers=list(supplier_values),
        criteria=list(CRITERIA),
        matrix=matrix,
        means=means,
        deviation_threshold=threshold,
    )


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, start=Decimal(0)) / Decimal(len(values))


def _cell(
    *,
    value: Decimal | None,
    mean: Decimal | None,
    comparable_count: int,
    deviation_threshold: Decimal = DEFAULT_DEVIATION_THRESHOLD,
) -> ComparisonCell:
    if value is None:
        return ComparisonCell(value=MISSING_DATA, note=MISSING_DATA)
    if comparable_count < 2 or mean is None:
        return ComparisonCell(value=_decimal_text(value), note=INSUFFICIENT_DATA)

    deviation_pct = Decimal(0) if mean == 0 else (value - mean) / mean * Decimal(100)
    return ComparisonCell(
        value=_decimal_text(value),
        deviation_pct=deviation_pct,
        highlight=abs(deviation_pct) > deviation_threshold * Decimal(100),
    )


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _supplier_id(supplier_name: str, supplier_ids: list[str] | None, index: int) -> str:
    if supplier_ids is not None and index < len(supplier_ids) and supplier_ids[index]:
        return supplier_ids[index]
    return supplier_name
