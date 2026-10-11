"""Kho lưu trữ Đơn mua hàng (PO nháp) - Spec 4.6.

Bền vững qua lần khởi động lại container, lưu trữ dưới dạng JSON trong data/purchase_orders.json.
"""

import json
import os
import threading
from pathlib import Path

from src.models.schemas import PurchaseOrder


class PurchaseOrderRepository:
    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self._lock = threading.Lock()

    def _load(self) -> list[PurchaseOrder]:
        if not self.storage_path.exists():
            return []
        with self.storage_path.open(encoding="utf-8") as file:
            return [PurchaseOrder.model_validate(record) for record in json.load(file)]

    def _save(self, orders: list[PurchaseOrder]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.storage_path.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(
                [order.model_dump(mode="json") for order in orders],
                file,
                ensure_ascii=False,
                indent=2,
            )
        os.replace(temporary_path, self.storage_path)

    def create(self, order: PurchaseOrder) -> PurchaseOrder:
        with self._lock:
            orders = self._load()
            existing = next((po for po in orders if po.id == order.id), None)
            if existing is not None:
                return existing
            existing_codes = {existing.code.lower() for existing in orders}
            if order.code.lower() in existing_codes:
                base_code = order.code
                counter = 1
                unique_code = f"{base_code}-{counter}"
                while unique_code.lower() in existing_codes:
                    counter += 1
                    unique_code = f"{base_code}-{counter}"
                order = order.model_copy(update={"code": unique_code})
            orders.append(order)
            self._save(orders)
            return order

    def list(self) -> list[PurchaseOrder]:
        return sorted(self._load(), key=lambda o: o.created_at, reverse=True)

    def get(self, po_id: str) -> PurchaseOrder | None:
        for order in self._load():
            if order.id == po_id or order.code.lower() == po_id.lower():
                return order
        return None

    def get_by_pr(self, pr_id: str) -> PurchaseOrder | None:
        for order in self._load():
            if order.pr_id == pr_id:
                return order
        return None


repository = PurchaseOrderRepository(Path("data/purchase_orders.json"))


def get_po_repository() -> PurchaseOrderRepository:
    return repository
