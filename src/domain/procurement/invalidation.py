"""Business rules for invalidating downstream procurement workflow steps."""

from enum import IntEnum

from pydantic import Field

from src.domain.common import ContractModel
from src.domain.purchase_request import PurchaseRequest, UpdatePurchaseRequest


class InvalidationLevel(IntEnum):
    """Describe how far a PR edit invalidates the five-step workflow."""

    METADATA = 0
    CONSTRAINTS = 1
    CALCULATION = 2
    STRUCTURE = 3


class PurchaseRequestChange(ContractModel):
    """One field-level change shown in the impact confirmation dialog."""

    field: str
    label: str
    before: str
    after: str
    level: InvalidationLevel
    scope: str


class PurchaseRequestImpact(ContractModel):
    """Server-owned impact assessment for an attempted PR update."""

    level: InvalidationLevel = InvalidationLevel.METADATA
    changes: list[PurchaseRequestChange] = Field(default_factory=list)
    analysis_becomes_stale: bool = False
    requires_quotation_reconfirmation: bool = False
    affected_steps: list[int] = Field(default_factory=list)


def _display(value: object) -> str:
    if value is None or value == "":
        return "—"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def assess_purchase_request_impact(
    current: PurchaseRequest,
    proposed: UpdatePurchaseRequest,
) -> PurchaseRequestImpact:
    """Classify a complete PR replacement using the approved reset matrix."""

    changes: list[PurchaseRequestChange] = []

    def add(field: str, label: str, before: object, after: object, level: InvalidationLevel, scope: str) -> None:
        if before == after:
            return
        changes.append(
            PurchaseRequestChange(
                field=field,
                label=label,
                before=_display(before),
                after=_display(after),
                level=level,
                scope=scope,
            )
        )

    add(
        "category",
        "Tên PR",
        current.category,
        proposed.category,
        InvalidationLevel.METADATA,
        "Cập nhật nhãn",
    )
    add(
        "estimated_budget",
        "Ngân sách dự kiến",
        current.estimated_budget,
        proposed.estimated_budget,
        InvalidationLevel.CONSTRAINTS,
        "Tính lại B4–B5",
    )
    add(
        "delivery_due_date",
        "Ngày nhận hàng",
        current.delivery_due_date,
        proposed.delivery_due_date,
        InvalidationLevel.CONSTRAINTS,
        "Đánh giá lại B4–B5",
    )
    add(
        "requested_quantity",
        "Tổng số lượng",
        current.requested_quantity,
        proposed.requested_quantity,
        InvalidationLevel.CALCULATION,
        "Tính lại B3–B5",
    )
    add(
        "requested_uom",
        "Đơn vị tính chung",
        current.requested_uom,
        proposed.requested_uom,
        InvalidationLevel.CALCULATION,
        "Đối soát lại B3–B5",
    )
    add(
        "target_currency",
        "Đồng tiền mục tiêu",
        current.target_currency,
        proposed.target_currency,
        InvalidationLevel.CALCULATION,
        "Tính lại B3–B5",
    )

    for field, label in (("department", "Phòng ban"), ("requested_by", "Người yêu cầu"), ("purpose", "Ghi chú / Mục đích")):
        add(
            f"metadata.{field}", label,
            getattr(current.metadata, field, None), getattr(proposed.metadata, field, None),
            InvalidationLevel.METADATA, "Cập nhật thông tin PR",
        )
    for field, label in (("budget", "Ngân sách bổ sung"), ("delivery_time", "Thời gian giao bổ sung")):
        add(
            f"metadata.{field}", label,
            getattr(current.metadata, field, None), getattr(proposed.metadata, field, None),
            InvalidationLevel.CONSTRAINTS, "Đánh giá lại B4–B5",
        )

    current_items = {item.item_id: item for item in current.items if item.item_id}
    proposed_items = {item.item_id: item for item in proposed.items if item.item_id}

    for item_id, item in current_items.items():
        updated = proposed_items.get(item_id)
        if updated is None:
            changes.append(
                PurchaseRequestChange(
                    field=f"items.{item_id}",
                    label=f"Xóa sản phẩm: {item.product_name}",
                    before=item.product_name,
                    after="Đã xóa",
                    level=InvalidationLevel.STRUCTURE,
                    scope="Đối soát lại B3; hủy B4–B5",
                )
            )
            continue
        add(
            f"items.{item_id}.product_name",
            f"Tên sản phẩm: {item.product_name}",
            item.product_name,
            updated.product_name,
            InvalidationLevel.STRUCTURE,
            "Đối soát lại B3; hủy B4–B5",
        )
        add(
            f"items.{item_id}.quantity",
            f"Số lượng: {item.product_name}",
            item.quantity,
            updated.quantity,
            InvalidationLevel.CALCULATION,
            "Tính lại B3–B5",
        )
        add(
            f"items.{item_id}.unit",
            f"Đơn vị: {item.product_name}",
            item.unit,
            updated.unit,
            InvalidationLevel.CALCULATION,
            "Đối soát lại B3–B5",
        )
        add(
            f"items.{item_id}.notes",
            f"Ghi chú: {item.product_name}",
            item.notes,
            updated.notes,
            InvalidationLevel.METADATA,
            "Cập nhật nhãn",
        )
        add(
            f"items.{item_id}.order_index",
            f"Thứ tự: {item.product_name}",
            item.order_index,
            updated.order_index,
            InvalidationLevel.STRUCTURE,
            "Đối soát lại B3; hủy B4–B5",
        )

    for item_id, item in proposed_items.items():
        if item_id in current_items:
            continue
        changes.append(
            PurchaseRequestChange(
                field=f"items.{item_id}",
                label=f"Thêm sản phẩm: {item.product_name}",
                before="—",
                after=item.product_name,
                level=InvalidationLevel.STRUCTURE,
                scope="Đối soát lại B3; hủy B4–B5",
            )
        )

    level = max((change.level for change in changes), default=InvalidationLevel.METADATA)
    affected_steps = {
        InvalidationLevel.METADATA: [5] if changes else [],
        InvalidationLevel.CONSTRAINTS: [4, 5],
        InvalidationLevel.CALCULATION: [3, 4, 5],
        InvalidationLevel.STRUCTURE: [3, 4, 5],
    }[level]
    return PurchaseRequestImpact(
        level=level,
        changes=changes,
        analysis_becomes_stale=bool(changes) and level >= InvalidationLevel.CONSTRAINTS,
        requires_quotation_reconfirmation=level >= InvalidationLevel.STRUCTURE,
        affected_steps=affected_steps,
    )


__all__ = [
    "InvalidationLevel",
    "PurchaseRequestChange",
    "PurchaseRequestImpact",
    "assess_purchase_request_impact",
]
