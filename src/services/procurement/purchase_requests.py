"""Kho lưu trữ PR tối giản, bền vững qua lần khởi động lại container.

MVP chưa có ORM/database service nên dùng JSON trong thư mục data đã được
Docker Compose mount. Có thể thay repository này bằng implementation PostgreSQL
mà không cần đổi API route.
"""

import json
import logging
import os
from pathlib import Path
from uuid import uuid4

from src.models.purchase_request import PRStatus, PurchaseRequest, PurchaseRequestCreate, PurchaseRequestUpdate
from src.services.auth import DemoUser

logger = logging.getLogger(__name__)


class PurchaseRequestRepository:
    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path

    def _load(self) -> list[PurchaseRequest]:
        if not self.storage_path.exists():
            return []
        with self.storage_path.open(encoding="utf-8") as file:
            data = json.load(file)
            requests = []
            for record in data:
                if "tenant_id" not in record:
                    record["tenant_id"] = "default-tenant"
                if "requested_quantity" not in record:
                    record["requested_quantity"] = record.get("quantity", 1)
                record.pop("quantity", None)
                if "requested_uom" not in record:
                    record["requested_uom"] = "Cái"
                if "target_currency" not in record:
                    record["target_currency"] = "VND"
                if "version" not in record:
                    record["version"] = 1
                if "updated_at" not in record:
                    record["updated_at"] = record.get("created_at")
                
                # Make naive datetimes timezone aware (assume UTC)
                for date_field in ["created_at", "updated_at"]:
                    if date_field in record and isinstance(record[date_field], str):
                        if not record[date_field].endswith("Z") and "+" not in record[date_field]:
                            record[date_field] += "Z"
                            
                requests.append(PurchaseRequest.model_validate(record))
            return requests

    def _save(self, requests: list[PurchaseRequest]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.storage_path.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(
                [request.model_dump(mode="json") for request in requests],
                file,
                ensure_ascii=False,
                indent=2,
            )
        os.replace(temporary_path, self.storage_path)

    def create(self, payload: PurchaseRequestCreate, creator: DemoUser, is_draft: bool = False) -> PurchaseRequest:
        requests = self._load()
        if any(request.code.lower() == payload.code.lower() for request in requests):
            raise ValueError("Mã PR đã tồn tại.")

        from datetime import datetime, UTC
        
        request = PurchaseRequest(
            id=str(uuid4()),
            tenant_id="default-tenant",
            code=payload.code.strip().upper(),
            creator_id=creator.id,
            creator_name=creator.name,
            category=payload.category.strip(),
            requested_quantity=getattr(payload, "quantity", None) or payload.requested_quantity,
            requested_uom=payload.requested_uom,
            target_currency=payload.target_currency,
            estimated_budget=payload.estimated_budget,
            delivery_due_date=payload.delivery_due_date,
            metadata=payload.metadata,
            items=payload.items,
            status=PRStatus.DRAFT if is_draft else PRStatus.AWAITING_QUOTATION,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC)
        )
        requests.append(request)
        self._save(requests)
        logger.info(
            "Purchase request created",
            extra={
                "event": "pr_created",
                "actor_id": creator.id,
                "actor_role": creator.role,
                "resource": "purchase_request",
                "resource_id": request.id,
                "new_status": request.status.value,
            },
        )
        return request

    def list(self, status: PRStatus | None = None) -> list[PurchaseRequest]:
        requests = self._load()
        filtered = [request for request in requests if status is None or request.status == status]
        return sorted(filtered, key=lambda request: request.created_at, reverse=True)

    def get(self, request_id: str) -> PurchaseRequest | None:
        return next((request for request in self._load() if request.id == request_id), None)

    def update(self, request_id: str, payload: PurchaseRequestUpdate) -> PurchaseRequest | None:
        """Update the editable PR fields without changing its workflow state."""
        requests = self._load()
        for index, request in enumerate(requests):
            if request.id != request_id:
                continue
            updated = request.model_copy(
                update={
                    "category": payload.category.strip(),
                    "requested_quantity": payload.requested_quantity,
                    "requested_uom": payload.requested_uom,
                    "target_currency": payload.target_currency,
                    "estimated_budget": payload.estimated_budget,
                    "delivery_due_date": payload.delivery_due_date,
                    "metadata": payload.metadata,
                    "items": payload.items,
                }
            )
            requests[index] = updated
            self._save(requests)
            return updated
        return None

    def delete(self, request_id: str) -> bool:
        """Remove a PR after its dependent quotation data has been removed."""
        requests = self._load()
        remaining = [request for request in requests if request.id != request_id]
        if len(remaining) == len(requests):
            return False
        self._save(remaining)
        return True

    def register_quotation(self, request_id: str) -> PurchaseRequest | None:
        """Được Feature upload gọi sau khi một báo giá được xác nhận."""
        requests = self._load()
        for index, request in enumerate(requests):
            if request.id != request_id:
                continue
            if request.status not in {PRStatus.AWAITING_QUOTATION, PRStatus.COMPARING}:
                raise ValueError("Không thể thêm báo giá cho PR ở trạng thái hiện tại.")
            updated = request.model_copy(
                update={
                    "quotation_count": request.quotation_count + 1,
                    "status": PRStatus.COMPARING,
                }
            )
            requests[index] = updated
            self._save(requests)
            return updated
        return None

    def set_quotation_count(self, request_id: str, count: int) -> PurchaseRequest | None:
        records = self._load()
        for index, request in enumerate(records):
            if request.id == request_id:
                request = request.model_copy(
                    update={
                        "quotation_count": count,
                        "status": PRStatus.COMPARING if count else PRStatus.AWAITING_QUOTATION,
                    }
                )
                records[index] = request
                self._save(records)
                return request
        return None

    def submit_for_approval(self, request_id: str) -> PurchaseRequest | None:
        """Chuyển PR đã có báo giá từ Đang so sánh sang Chờ duyệt."""
        requests = self._load()
        for index, request in enumerate(requests):
            if request.id != request_id:
                continue
            if request.status != PRStatus.COMPARING:
                raise ValueError("PR cần có ít nhất một báo giá trước khi gửi duyệt.")
            # A fresh submission acknowledges that the Buyer addressed any
            # prior manager rejection; do not keep an obsolete warning visible.
            updated = request.model_copy(update={"status": PRStatus.PENDING_APPROVAL, "rejection_reason": None})
            requests[index] = updated
            self._save(requests)
            logger.info(
                "Purchase request submitted for approval",
                extra={
                    "event": "pr_submitted_for_approval",
                    "resource": "purchase_request",
                    "resource_id": request.id,
                    "previous_status": request.status.value,
                    "new_status": updated.status.value,
                },
            )
            return updated
        return None

    def approve(self, request_id: str, po_id: str) -> PurchaseRequest | None:
        """Quản lý duyệt PR (Spec 4.6), chuyển trạng thái sang Đã duyệt và liên kết PO nháp."""
        requests = self._load()
        for index, request in enumerate(requests):
            if request.id != request_id:
                continue
            if request.status != PRStatus.PENDING_APPROVAL:
                raise ValueError("Chỉ có thể phê duyệt PR đang ở trạng thái Chờ duyệt.")
            updated = request.model_copy(update={"status": PRStatus.APPROVED, "po_id": po_id})
            requests[index] = updated
            self._save(requests)
            logger.info(
                "Purchase request approved",
                extra={
                    "event": "pr_approved",
                    "resource": "purchase_request",
                    "resource_id": request.id,
                    "previous_status": request.status.value,
                    "new_status": updated.status.value,
                },
            )
            return updated
        return None

    def reject(self, request_id: str, reason: str) -> PurchaseRequest | None:
        """Quản lý từ chối PR (Spec 4.6), đưa PR quay lại trạng thái Đang so sánh kèm lý do."""
        requests = self._load()
        for index, request in enumerate(requests):
            if request.id != request_id:
                continue
            if request.status != PRStatus.PENDING_APPROVAL:
                raise ValueError("Chỉ có thể từ chối PR đang ở trạng thái Chờ duyệt.")
            updated = request.model_copy(update={"status": PRStatus.COMPARING, "rejection_reason": reason.strip()})
            requests[index] = updated
            self._save(requests)
            logger.info(
                "Purchase request rejected",
                extra={
                    "event": "pr_rejected",
                    "resource": "purchase_request",
                    "resource_id": request.id,
                    "previous_status": request.status.value,
                    "new_status": updated.status.value,
                },
            )
            return updated
        return None

    def reset_stale_approval(self, request_id: str, reason: str) -> PurchaseRequest | None:
        """Reopen a legacy, unverified approval queue entry for a new analysis."""
        requests = self._load()
        for index, request in enumerate(requests):
            if request.id != request_id:
                continue
            if request.status != PRStatus.PENDING_APPROVAL:
                return request
            updated = request.model_copy(update={"status": PRStatus.COMPARING, "rejection_reason": reason})
            requests[index] = updated
            self._save(requests)
            return updated
        return None


repository = PurchaseRequestRepository(Path("data/purchase_requests.json"))


def get_pr_repository() -> PurchaseRequestRepository:
    return repository
