"""Kho lưu trữ Đơn mua hàng (PO nháp) - Spec 4.6.

Bền vững qua lần khởi động lại container, lưu trữ dưới dạng JSON trong data/purchase_orders.json.
"""

import json
import os
import threading
from pathlib import Path
from typing import Literal

from src.domain.procurement.contracts import PurchaseOrder, PurchaseOrderPage
from src.infrastructure.persistence.postgres import PostgresRecordStore


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

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        query: str = "",
        supplier: str = "",
        sort_by: Literal["code", "pr_code", "supplier_name", "approver_name", "approved_at", "total_amount"] = "approved_at",
        sort_direction: Literal["asc", "desc"] = "desc",
    ) -> PurchaseOrderPage:
        all_orders = self._load()
        orders = all_orders
        normalized_query = query.strip().casefold()
        if normalized_query:
            orders = [
                order for order in orders
                if any(normalized_query in str(value or "").casefold() for value in (
                    order.code, order.pr_code, order.supplier_name, order.approver_name
                ))
            ]
        if supplier:
            normalized_supplier = supplier.casefold()
            orders = [order for order in orders if order.supplier_name.casefold() == normalized_supplier]

        suppliers = sorted({order.supplier_name for order in all_orders if order.supplier_name.casefold()}, key=str.casefold)
        key_getters = {
            "code": lambda order: order.code.casefold(),
            "pr_code": lambda order: order.pr_code.casefold(),
            "supplier_name": lambda order: order.supplier_name.casefold(),
            "approver_name": lambda order: order.approver_name.casefold(),
            "approved_at": lambda order: order.approved_at,
            "total_amount": lambda order: order.total_amount,
        }
        orders.sort(key=key_getters[sort_by], reverse=sort_direction == "desc")
        total = len(orders)
        effective_page = min(page, max(1, (total + page_size - 1) // page_size))
        start = (effective_page - 1) * page_size
        return PurchaseOrderPage(
            items=orders[start:start + page_size],
            page=effective_page,
            page_size=page_size,
            total=total,
            suppliers=suppliers,
        )

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


class PostgresPurchaseOrderRepository(PurchaseOrderRepository):
    """Keep the PO repository API while using PostgreSQL as system of record."""

    def __init__(self, database_url: str) -> None:
        self.store = PostgresRecordStore(database_url)
        self._lock = threading.Lock()

    def _load(self) -> list[PurchaseOrder]:
        return [PurchaseOrder.model_validate(record) for record in self.store.load("purchase_orders")]

    def _save(self, orders: list[PurchaseOrder]) -> None:
        self.store.replace("purchase_orders", (order.model_dump(mode="json") for order in orders), parent_key="pr_id")

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        query: str = "",
        supplier: str = "",
        sort_by: Literal["code", "pr_code", "supplier_name", "approver_name", "approved_at", "total_amount"] = "approved_at",
        sort_direction: Literal["asc", "desc"] = "desc",
    ) -> PurchaseOrderPage:
        where = ["namespace = %s"]
        parameters: list[object] = ["purchase_orders"]
        if query.strip():
            where.append("(payload->>'code' ILIKE %s OR payload->>'pr_code' ILIKE %s OR payload->>'supplier_name' ILIKE %s OR payload->>'approver_name' ILIKE %s)")
            pattern = f"%{query.strip()}%"
            parameters.extend([pattern, pattern, pattern, pattern])
        if supplier:
            where.append("lower(payload->>'supplier_name') = lower(%s)")
            parameters.append(supplier)
        where_sql = " AND ".join(where)
        sort_expressions = {
            "code": "lower(payload->>'code')",
            "pr_code": "lower(payload->>'pr_code')",
            "supplier_name": "lower(payload->>'supplier_name')",
            "approver_name": "lower(payload->>'approver_name')",
            "approved_at": "(payload->>'approved_at')::timestamptz",
            "total_amount": "(payload->>'total_amount')::numeric",
        }
        direction = "ASC" if sort_direction == "asc" else "DESC"
        with self.store.transaction() as connection:
            total = connection.execute(
                f"SELECT count(*) AS total FROM application_records WHERE {where_sql}", parameters
            ).fetchone()["total"]
            effective_page = min(page, max(1, (int(total) + page_size - 1) // page_size))
            offset = (effective_page - 1) * page_size
            rows = connection.execute(
                f"SELECT payload FROM application_records WHERE {where_sql} ORDER BY {sort_expressions[sort_by]} {direction} NULLS LAST, record_id ASC LIMIT %s OFFSET %s",
                [*parameters, page_size, offset],
            ).fetchall()
            supplier_rows = connection.execute(
                "SELECT DISTINCT payload->>'supplier_name' AS supplier_name FROM application_records WHERE namespace = %s AND COALESCE(payload->>'supplier_name', '') <> '' ORDER BY supplier_name",
                ("purchase_orders",),
            ).fetchall()
        return PurchaseOrderPage(
            items=[PurchaseOrder.model_validate(row["payload"]) for row in rows],
            page=effective_page,
            page_size=page_size,
            total=int(total),
            suppliers=[row["supplier_name"] for row in supplier_rows],
        )


repository: PurchaseOrderRepository | None = None


def get_po_repository() -> PurchaseOrderRepository:
    global repository
    if repository is None:
        from src.core.config import get_settings

        settings = get_settings()
        repository = (
            PostgresPurchaseOrderRepository(settings.database_url)
            if settings.persistence_backend == "postgresql"
            else PurchaseOrderRepository(Path("data/purchase_orders.json"))
        )
    return repository
