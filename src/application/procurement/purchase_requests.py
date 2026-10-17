"""Application service for editing a PR without losing downstream source data."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace
from uuid import uuid4

from src.domain.fuzzy_match import MatchStatus
from src.domain.matching import PRItem as FuzzyPRItem
from src.domain.matching import ProductMatchingService, QuoteItemInput
from src.domain.procurement.invalidation import (
    InvalidationLevel,
    PurchaseRequestImpact,
    assess_purchase_request_impact,
)
from src.domain.purchase_request import PRItem, PRStatus, PurchaseRequest, UpdatePurchaseRequest
from src.domain.quotation.confirmation import Quotation, QuotationStatus
from src.infrastructure.quotation.repository import QuotationRepository
from src.infrastructure.repositories.purchase_requests import PurchaseRequestRepository

logger = logging.getLogger(__name__)
MONEY_QUANTUM = Decimal("0.01")


class PurchaseRequestUpdateError(Exception):
    """Base class for errors that the HTTP boundary maps explicitly."""


class PurchaseRequestNotFoundError(PurchaseRequestUpdateError):
    """Raised when the target PR no longer exists."""


class PurchaseRequestLockedError(PurchaseRequestUpdateError):
    """Raised when approval state makes a PR immutable."""


class PurchaseRequestConflictError(PurchaseRequestUpdateError):
    """Raised when optimistic version validation fails."""


class PurchaseRequestPayloadError(PurchaseRequestUpdateError):
    """Raised when a complete update payload is internally inconsistent."""


@dataclass(frozen=True)
class PurchaseRequestUpdateResult:
    request: PurchaseRequest
    impact: PurchaseRequestImpact


def _normalized_payload(current: PurchaseRequest, payload: UpdatePurchaseRequest) -> UpdatePurchaseRequest:
    category = payload.category.strip()
    requested_uom = payload.requested_uom.strip()
    target_currency = payload.target_currency.strip().upper()
    if not category or not requested_uom or not target_currency:
        raise PurchaseRequestPayloadError("Tên PR, đơn vị tính và đồng tiền mục tiêu không được để trống.")
    current_by_position = {item.order_index: item for item in current.items}
    normalized: list[PRItem] = []
    seen: set[str] = set()
    for item in payload.items:
        product_name = item.product_name.strip()
        unit = item.unit.strip()
        if not product_name or not unit:
            raise PurchaseRequestPayloadError("Tên sản phẩm và đơn vị tính không được để trống.")
        item_id = item.item_id
        if item_id is None:
            previous = current_by_position.get(item.order_index)
            item_id = previous.item_id if previous is not None else str(uuid4())
        if item_id in seen:
            raise PurchaseRequestPayloadError("Mỗi dòng sản phẩm phải có mã định danh duy nhất.")
        seen.add(item_id)
        normalized.append(
            item.model_copy(
                update={
                    "item_id": item_id,
                    "product_name": product_name,
                    "unit": unit,
                }
            )
        )

    if normalized:
        item_total = sum((item.quantity for item in normalized), Decimal(0))
        if item_total != payload.requested_quantity:
            raise PurchaseRequestPayloadError("Tổng số lượng PR phải bằng tổng số lượng của các dòng sản phẩm.")
    return payload.model_copy(
        update={
            "category": category,
            "requested_uom": requested_uom,
            "target_currency": target_currency,
            "items": normalized,
        }
    )


def preview_purchase_request_update(
    current: PurchaseRequest,
    payload: UpdatePurchaseRequest,
) -> tuple[UpdatePurchaseRequest, PurchaseRequestImpact]:
    """Normalize stable item IDs and return the authoritative change impact."""

    normalized = _normalized_payload(current, payload)
    return normalized, assess_purchase_request_impact(current, normalized)


def _recalculate_quotations(
    current: PurchaseRequest,
    proposed: UpdatePurchaseRequest,
    quotations: list[Quotation],
    *,
    next_pr_version: int,
) -> list[Quotation]:
    current_by_id = {item.item_id: item for item in current.items if item.item_id}
    proposed_by_id = {item.item_id: item for item in proposed.items if item.item_id}
    changed_ids = {
        item_id
        for item_id, item in current_by_id.items()
        if item_id in proposed_by_id
        and (item.quantity != proposed_by_id[item_id].quantity or item.unit != proposed_by_id[item_id].unit)
    }
    if not changed_ids:
        return []

    matchable_items = [
        FuzzyPRItem(id=item_id, name=item.product_name, uom=item.unit, description=item.notes)
        for item_id, item in current_by_id.items()
    ]
    matcher = ProductMatchingService()
    replacements: list[Quotation] = []
    recalculated_at = datetime.now(UTC).isoformat()

    for quotation in quotations:
        if quotation.status != QuotationStatus.CONFIRMED:
            continue
        changed_lines = []
        updated_items = []
        for index, quote_item in enumerate(quotation.items):
            if quote_item.match_status == MatchStatus.MANUAL_MATCHED and quote_item.matched_pr_item_id:
                candidate = next(
                    (item for item in matchable_items if item.id == quote_item.matched_pr_item_id),
                    None,
                )
                candidate = (
                    SimpleNamespace(pr_item_id=candidate.id, status=MatchStatus.MANUAL_MATCHED)
                    if candidate is not None
                    else None
                )
            else:
                match = matcher.match_one(
                    QuoteItemInput(
                        id=f"{quotation.id}:item:{index}",
                        name=quote_item.product_name,
                        uom=quote_item.unit,
                    ),
                    matchable_items,
                )
                candidate = match.best_match
            if (
                candidate is None
                or candidate.status not in {MatchStatus.AUTO_MATCHED, MatchStatus.MANUAL_MATCHED}
                or candidate.pr_item_id not in changed_ids
            ):
                updated_items.append(quote_item)
                continue

            target = proposed_by_id[candidate.pr_item_id]
            integral_quantity = int(target.quantity)
            if Decimal(integral_quantity) != target.quantity:
                raise PurchaseRequestPayloadError(
                    "Báo giá hiện chỉ hỗ trợ số lượng nguyên; hãy đối soát lại dòng sản phẩm trước khi lưu."
                )
            updated_item = quote_item.model_copy(
                update={
                    "quantity": integral_quantity,
                    "unit": target.unit,
                    "line_total": (quote_item.unit_price * target.quantity).quantize(
                        MONEY_QUANTUM,
                        rounding=ROUND_HALF_UP,
                    ),
                }
            )
            updated_items.append(updated_item)
            changed_lines.append(
                {
                    "quote_item_index": index,
                    "pr_item_id": candidate.pr_item_id,
                    "before_quantity": str(quote_item.quantity),
                    "after_quantity": str(target.quantity),
                    "before_unit": quote_item.unit,
                    "after_unit": target.unit,
                    "before_line_total": str(quote_item.line_total),
                    "after_line_total": str(updated_item.line_total),
                }
            )

        if not changed_lines:
            continue
        factor = Decimal(1)
        if quotation.vat_included is False and quotation.vat_rate is not None:
            factor += quotation.vat_rate
        goods_total = sum((item.line_total for item in updated_items), Decimal(0))
        goods_total = (goods_total * factor).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        audit = dict(quotation.confirmation_audit or {})
        recalculations = list(audit.get("pr_recalculations") or [])
        recalculations.append(
            {
                "at": recalculated_at,
                "pr_id": current.id,
                "pr_version": next_pr_version,
                "lines": changed_lines,
            }
        )
        audit["pr_recalculations"] = recalculations
        replacements.append(
            quotation.model_copy(
                update={
                    "items": updated_items,
                    "goods_total_including_tax": goods_total,
                    "confirmation_audit": audit,
                }
            )
        )
    return replacements


def update_purchase_request(
    request_id: str,
    payload: UpdatePurchaseRequest,
    *,
    pr_repository: PurchaseRequestRepository,
    quotation_repository: QuotationRepository,
    actor_id: str,
    actor_role: str,
    expected_version: int | None = None,
) -> PurchaseRequestUpdateResult:
    """Apply a PR update and enforce the reset matrix on dependent quotations."""

    current = pr_repository.get(request_id)
    if current is None:
        raise PurchaseRequestNotFoundError("Không tìm thấy PR.")
    if current.status in {PRStatus.PENDING_APPROVAL, PRStatus.APPROVED}:
        raise PurchaseRequestLockedError("PR đang chờ duyệt hoặc đã được phê duyệt nên không thể chỉnh sửa.")
    if expected_version is not None and current.version != expected_version:
        raise PurchaseRequestConflictError("PR đã được cập nhật ở phiên khác. Hãy tải lại dữ liệu trước khi lưu.")

    normalized, impact = preview_purchase_request_update(current, payload)
    if not impact.changes:
        return PurchaseRequestUpdateResult(request=current, impact=impact)

    quotations = quotation_repository.list_for_pr(request_id)
    recalculated = []
    if impact.level == InvalidationLevel.CALCULATION:
        recalculated = _recalculate_quotations(
            current,
            normalized,
            quotations,
            next_pr_version=current.version + 1,
        )

    try:
        updated = pr_repository.update(request_id, normalized, expected_version=current.version)
    except ValueError as error:
        raise PurchaseRequestConflictError(str(error)) from error
    if updated is None:
        raise PurchaseRequestNotFoundError("Không tìm thấy PR.")

    if impact.level >= InvalidationLevel.STRUCTURE:
        quotation_repository.reopen_confirmed_for_pr(request_id)
        confirmed_count = sum(
            quote.status == QuotationStatus.CONFIRMED for quote in quotation_repository.list_for_pr(request_id)
        )
        updated = pr_repository.set_quotation_count(request_id, confirmed_count) or updated
    elif recalculated:
        quotation_repository.replace_many(recalculated)

    logger.info(
        "Purchase request updated with downstream invalidation",
        extra={
            "event": "pr_updated",
            "actor_id": actor_id,
            "actor_role": actor_role,
            "resource": "purchase_request",
            "resource_id": request_id,
            "previous_version": current.version,
            "new_version": updated.version,
            "invalidation_level": int(impact.level),
            "changed_fields": [change.field for change in impact.changes],
        },
    )
    return PurchaseRequestUpdateResult(request=updated, impact=impact)


__all__ = [
    "PurchaseRequestConflictError",
    "PurchaseRequestLockedError",
    "PurchaseRequestNotFoundError",
    "PurchaseRequestPayloadError",
    "PurchaseRequestUpdateResult",
    "preview_purchase_request_update",
    "update_purchase_request",
]
