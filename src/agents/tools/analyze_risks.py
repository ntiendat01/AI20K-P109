from __future__ import annotations

from datetime import date, timedelta
from typing import assert_never

from src.domain.agent.analysis.normalization import (
    NormalizationStatus,
    NormalizedQuotationArtifact,
)
from src.domain.agent.analysis.risk import RiskFlag, RiskSeverity
from src.domain.agent.quotation.confirmation import QuotationConfirmationRequest


def analyze_risks(
    normalized_quotes: list[NormalizedQuotationArtifact],
    confirmed_quotes: list[QuotationConfirmationRequest],
    delivery_due_date: date | None,
    *,
    supplier_ids: list[str] | None = None,
) -> list[RiskFlag]:
    risk_flags: list[RiskFlag] = []
    days_remaining = _calculate_working_days(date.today(), delivery_due_date) if delivery_due_date is not None else None

    for index, (normalized, confirmed) in enumerate(zip(normalized_quotes, confirmed_quotes, strict=True)):
        supplier_id = _supplier_id(confirmed.supplier_name, supplier_ids, index)
        match normalized.status:
            case NormalizationStatus.NORMALIZED:
                pass
            case NormalizationStatus.NEEDS_MAPPING:
                risk_flags.append(
                    RiskFlag(
                        supplier_id=supplier_id,
                        risk_type="normalization_mapping_required",
                        severity=RiskSeverity.HIGH,
                        description="Báo giá còn dữ liệu chưa thể chuẩn hóa tự động",
                        details={"issues": normalized.issues},
                    )
                )
            case unreachable:
                assert_never(unreachable)

        if days_remaining is not None and confirmed.lead_time_days > days_remaining:
            delta = confirmed.lead_time_days - days_remaining
            risk_flags.append(
                RiskFlag(
                    supplier_id=supplier_id,
                    risk_type="lead_time_exceeded",
                    severity=RiskSeverity.HIGH,
                    description=f"Vượt hạn giao {delta} ngày làm việc",
                    details={
                        "lead_time_days": confirmed.lead_time_days,
                        "days_remaining": days_remaining,
                        "delta": delta,
                    },
                )
            )

    return risk_flags


def _supplier_id(supplier_name: str, supplier_ids: list[str] | None, index: int) -> str:
    if supplier_ids is not None and index < len(supplier_ids) and supplier_ids[index]:
        return supplier_ids[index]
    return supplier_name


def _calculate_working_days(start_date: date, end_date: date) -> int:
    day_count = (end_date - start_date).days
    if day_count == 0:
        return 0

    direction = 1 if day_count > 0 else -1
    current = start_date
    working_days = 0
    for _ in range(abs(day_count)):
        current += timedelta(days=direction)
        if current.weekday() < 5:
            working_days += direction
    return working_days
