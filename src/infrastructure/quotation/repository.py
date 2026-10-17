"""Kho quotation và file gốc cho MVP."""
# allow: SIZE_OK -- quotation metadata and its source-file lifecycle share persistence invariants.

import hashlib
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from src.application.quotation.parser import ExtractedQuotation
from src.domain.fuzzy_match import MatchStatus
from src.domain.quotation.confirmation import Quotation, QuotationConfirmation, QuotationStatus
from src.infrastructure.persistence.postgres import PostgresRecordStore
from src.infrastructure.ocr.client import OCRServiceError, RemoteOCRClient
from src.infrastructure.storage import FilesystemObjectStorage, ObjectStorage, S3ObjectStorage

logger = logging.getLogger(__name__)


def source_text(path: str) -> str:
    """Retain actual source text for audit; never reconstruct it from model output."""
    source = Path(path)
    try:
        if source.suffix.lower() == ".pdf":
            return RemoteOCRClient.from_settings().native_pdf_text(source.read_bytes())
        return source.read_text(encoding="utf-8", errors="replace")
    except OCRServiceError as error:
        if error.retryable:
            raise
        logger.warning("Quotation source was rejected by OCR service", extra={"file_name": source.name})
        return ""
    except (OSError, RuntimeError, ValueError) as error:
        logger.warning(
            "Quotation source could not be read",
            extra={
                "event": "quotation_source_read_failed",
                "error_type": type(error).__name__,
                "file_name": source.name,
                "storage_backend": "filesystem",
            },
        )
        return ""


class QuotationRepository:
    def __init__(self, storage_path: Path, upload_root: Path, object_storage: ObjectStorage | None = None) -> None:
        self.storage_path = storage_path
        self.upload_root = upload_root
        self.object_storage = object_storage or FilesystemObjectStorage(upload_root)

    def _serialize(self, quotation: Quotation) -> dict:
        data = quotation.model_dump(mode="json")
        data["source_path"] = quotation.source_path
        data["confirmation_audit"] = quotation.confirmation_audit
        data["source_ocr_text"] = quotation.source_ocr_text
        return data

    def _load(self) -> list[Quotation]:
        if not self.storage_path.exists():
            return []
        try:
            with self.storage_path.open(encoding="utf-8") as file:
                return [Quotation.model_validate(record) for record in json.load(file)]
        except (json.JSONDecodeError, OSError):
            logger.exception(
                "Quotation storage could not be read",
                extra={
                    "event": "quotation_storage_read_failed",
                    "file_name": self.storage_path.name,
                    "storage_backend": "filesystem",
                },
            )
            raise

    def _save(self, quotations: list[Quotation]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.storage_path.with_suffix(".tmp")
        try:
            with temporary_path.open("w", encoding="utf-8") as file:
                json.dump([self._serialize(quotation) for quotation in quotations], file, ensure_ascii=False, indent=2)
            os.replace(temporary_path, self.storage_path)
        except OSError:
            logger.exception(
                "Quotation storage could not be written",
                extra={
                    "event": "quotation_storage_write_failed",
                    "file_name": self.storage_path.name,
                    "storage_backend": "filesystem",
                },
            )
            raise

    def list_for_pr(self, pr_id: str) -> list[Quotation]:
        return sorted(
            [quotation for quotation in self._load() if quotation.pr_id == pr_id],
            key=lambda quotation: quotation.created_at,
            reverse=True,
        )

    def get(self, quotation_id: str) -> Quotation | None:
        return next((quotation for quotation in self._load() if quotation.id == quotation_id), None)

    def delete(self, quotation_id: str) -> Quotation | None:
        """Remove one quotation and its source file when no record still uses it."""
        quotations = self._load()
        quotation = next((record for record in quotations if record.id == quotation_id), None)
        if quotation is None:
            return None

        remaining = [record for record in quotations if record.id != quotation_id]
        self._save(remaining)

        if not any(record.source_path == quotation.source_path for record in remaining):
            self.object_storage.delete(quotation.source_path)
        return quotation

    def delete_for_pr(self, pr_id: str) -> int:
        """Delete all quotations and their source files belonging to one PR."""
        quotations = self._load()
        targets = [quotation for quotation in quotations if quotation.pr_id == pr_id]

        # PR IDs are UUIDs created by this service; reject a path-shaped ID as
        # an extra guard before deleting object keys for this request.
        if Path(pr_id).name != pr_id:
            raise ValueError("Mã đề nghị mua không hợp lệ.")
        for quotation in targets:
            self.object_storage.delete(quotation.source_path)

        if targets:
            self._save([quotation for quotation in quotations if quotation.pr_id != pr_id])
        return len(targets)

    def cached_extraction(self, source_hash: str, extraction_version: int) -> Quotation | None:
        return next(
            (
                quotation
                for quotation in self._load()
                if quotation.source_hash == source_hash
                and quotation.extraction_version == extraction_version
                and quotation.extraction_mode == "parser"
                and quotation.status != "confirmed"
            ),
            None,
        )

    def save_upload(
        self,
        *,
        pr_id: str,
        supplier_name: str,
        source_filename: str,
        source_content_type: str,
        content: bytes,
        extracted: ExtractedQuotation,
        cache_hit: bool,
        extraction_version: int,
    ) -> Quotation:
        source_hash = hashlib.sha256(content).hexdigest()
        suffix = Path(source_filename).suffix.lower()
        stored_filename = f"{source_hash}{suffix}"
        source_key = f"{pr_id}/{stored_filename}"
        source_path = str(self.upload_root / source_key)
        if not self.object_storage.exists(source_path):
            try:
                source_path = self.object_storage.put(source_key, content, source_content_type)
            except (OSError, RuntimeError):
                logger.exception(
                    "Quotation source could not be written",
                    extra={
                        "event": "quotation_source_write_failed",
                        "file_name": stored_filename,
                        "resource": "purchase_request",
                        "resource_id": pr_id,
                        "storage_backend": "filesystem",
                    },
                )
                raise
        quotation = Quotation(
            id=str(uuid4()),
            pr_id=pr_id,
            supplier_name=supplier_name,
            source_filename=Path(source_filename).name,
            source_hash=source_hash,
            source_path=source_path,
            source_content_type=source_content_type or "application/octet-stream",
            extraction_version=extraction_version,
            delivery_time=extracted.delivery_time,
            payment_terms=extracted.payment_terms,
            warranty=extracted.warranty,
            currency=extracted.currency,
            items=extracted.items,
            extraction_warnings=extracted.warnings,
            cache_hit=cache_hit,
        )
        quotations = self._load()
        quotations.append(quotation)
        self._save(quotations)
        return quotation

    def confirm(
        self, quotation_id: str, payload: QuotationConfirmation, *, actor_id: str | None = None
    ) -> Quotation | None:
        quotations = self._load()
        for index, quotation in enumerate(quotations):
            if quotation.id != quotation_id:
                continue
            if quotation.status == QuotationStatus.CONFIRMED:
                raise ValueError("Báo giá này đã được xác nhận.")
            agent_lines = quotation.agent_extractions
            if quotation.extraction_mode == "agent":
                from src.application.quotation.intake import resume_confirmation

                agent_lines = resume_confirmation(quotation, payload)
            normalized_name = " ".join(payload.supplier_name.casefold().split())
            supplier_id = next(
                (
                    q.supplier_id
                    for q in quotations
                    if q.supplier_id and " ".join(q.supplier_name.casefold().split()) == normalized_name
                ),
                None,
            )
            supplier_id = supplier_id or quotation.supplier_id or str(uuid4())
            updated = quotation.model_copy(
                update={
                    "supplier_id": supplier_id,
                    "agent_extractions": agent_lines,
                    **payload.model_dump(exclude_unset=True),
                    "supplier_name": payload.supplier_name.strip(),
                    "confirmation_audit": {
                        "audit_id": str(uuid4()),
                        "actor_id": actor_id,
                        "confirmed_at": datetime.now().isoformat(),
                        "source_text": self.source_text(quotation) or quotation.source_ocr_text or "",
                        "before": quotation.model_dump(mode="json"),
                        "submitted": payload.model_dump(mode="json", exclude_unset=True),
                    },
                    "delivery_time": f"{payload.lead_time_days} ngày lịch sau xác nhận đơn hàng"
                    if payload.lead_time_days is not None
                    else payload.delivery_time.strip(),
                    "warranty": f"{payload.warranty_months} tháng"
                    if payload.warranty_months is not None
                    else quotation.warranty,
                    "payment_terms": payload.payment_terms.strip(),
                    "items": payload.items,
                    "status": QuotationStatus.CONFIRMED,
                    "confirmed_at": datetime.now(),
                    "extraction_warnings": [],
                }
            )
            quotations[index] = updated
            self._save(quotations)
            return updated
        return None

    def reopen(self, quotation_id: str) -> Quotation | None:
        records = self._load()
        for index, quote in enumerate(records):
            if quote.id == quotation_id:
                quote = quote.model_copy(update={"status": QuotationStatus.UNCONFIRMED, "confirmed_at": None})
                records[index] = quote
                self._save(records)
                return quote
        return None

    def reopen_confirmed_for_pr(self, pr_id: str) -> list[Quotation]:
        """Reopen every confirmed quotation after a structural PR change."""
        records = self._load()
        reopened: list[Quotation] = []
        for index, quote in enumerate(records):
            if quote.pr_id != pr_id or quote.status != QuotationStatus.CONFIRMED:
                continue
            updated = quote.model_copy(
                update={
                    "status": QuotationStatus.UNCONFIRMED,
                    "confirmed_at": None,
                    "items": [item.model_copy(update={"matched_pr_item_id": None, "match_status": None}) for item in quote.items],
                }
            )
            records[index] = updated
            reopened.append(updated)
        if reopened:
            self._save(records)
        return reopened

    def set_item_match(
        self, quotation_id: str, item_index: int, *, pr_item_id: str | None, match_status: MatchStatus
    ) -> Quotation | None:
        """Persist a buyer-reviewed mapping on one confirmed quotation line."""
        records = self._load()
        for index, quote in enumerate(records):
            if quote.id != quotation_id:
                continue
            if quote.status != QuotationStatus.CONFIRMED:
                raise ValueError("Chỉ có thể ghép dòng hàng của báo giá đã xác nhận.")
            if item_index < 0 or item_index >= len(quote.items):
                raise ValueError("Không tìm thấy dòng hàng trong báo giá.")
            items = list(quote.items)
            items[item_index] = items[item_index].model_copy(
                update={"matched_pr_item_id": pr_item_id, "match_status": match_status}
            )
            updated = quote.model_copy(update={"items": items})
            records[index] = updated
            self._save(records)
            return updated
        return None

    def replace_many(self, replacements: list[Quotation]) -> list[Quotation]:
        """Persist a server-calculated update to several quotations atomically per repository save."""
        if not replacements:
            return []
        replacement_by_id = {quotation.id: quotation for quotation in replacements}
        records = self._load()
        found: set[str] = set()
        for index, quote in enumerate(records):
            replacement = replacement_by_id.get(quote.id)
            if replacement is None:
                continue
            if replacement.pr_id != quote.pr_id:
                raise ValueError("Không thể chuyển báo giá sang PR khác.")
            records[index] = replacement
            found.add(quote.id)
        if found != set(replacement_by_id):
            raise ValueError("Một hoặc nhiều báo giá cần cập nhật không còn tồn tại.")
        self._save(records)
        return replacements

    def replace_extraction(
        self,
        quotation_id: str,
        extracted: ExtractedQuotation,
        extraction_version: int,
    ) -> Quotation | None:
        """Replace an unconfirmed draft with a newer parser's extraction."""
        quotations = self._load()
        for index, quotation in enumerate(quotations):
            if quotation.id != quotation_id:
                continue
            updated = quotation.model_copy(
                update={
                    "supplier_name": extracted.supplier_name or quotation.supplier_name,
                    "delivery_time": extracted.delivery_time,
                    "payment_terms": extracted.payment_terms,
                    "warranty": extracted.warranty,
                    "currency": extracted.currency,
                    "items": extracted.items,
                    "extraction_warnings": extracted.warnings,
                    "cache_hit": False,
                    "extraction_version": extraction_version,
                }
            )
            quotations[index] = updated
            self._save(quotations)
            return updated
        return None

    def apply_agent_extraction(self, quotation_id, extracted, raw, ocr_text: str):
        quote = self.replace_extraction(quotation_id, extracted, 4)
        records = self._load()
        for i, q in enumerate(records):
            if q.id == quotation_id:
                first = raw[0] if raw else {}
                quote = q.model_copy(
                    update={
                        "extraction_mode": "agent",
                        "agent_extractions": raw,
                        "source_ocr_text": ocr_text,
                        "vat_rate": Decimal(str(first["vat_rate"])) if first.get("vat_rate") is not None else None,
                        "vat_included": first.get("vat_included"),
                        "shipping_fee": sum(
                            Decimal(str(x["amount"]))
                            for x in first.get("surcharges", [])
                            if x.get("amount") is not None
                        )
                        if first.get("surcharges")
                        else None,
                        "lead_time_days": first.get("lead_time_days"),
                        "warranty_months": first.get("warranty_months"),
                        "payment_terms": extracted.payment_terms or first.get("payment_terms") or q.payment_terms,
                    }
                )
                records[i] = quote
                self._save(records)
                return quote
        return quote

    def source_exists(self, quotation: Quotation) -> bool:
        return self.object_storage.exists(quotation.source_path)

    def read_source(self, quotation: Quotation) -> bytes:
        return self.object_storage.get(quotation.source_path)

    @contextmanager
    def materialize_source(self, quotation: Quotation):
        with self.object_storage.materialize(quotation.source_path, quotation.source_filename) as path:
            yield path

    def source_text(self, quotation: Quotation) -> str:
        with self.materialize_source(quotation) as path:
            return source_text(str(path))


class PostgresQuotationRepository(QuotationRepository):
    """Quotation metadata in PostgreSQL; original documents stay in object storage."""

    def __init__(self, database_url: str, object_storage: ObjectStorage) -> None:
        self.store = PostgresRecordStore(database_url)
        self.upload_root = Path("data/uploads")
        self.object_storage = object_storage

    def _load(self) -> list[Quotation]:
        return [Quotation.model_validate(record) for record in self.store.load("quotations")]

    def _save(self, quotations: list[Quotation]) -> None:
        self.store.replace(
            "quotations", (self._serialize(quotation) for quotation in quotations), parent_key="pr_id"
        )


repository: QuotationRepository | None = None


def get_quotation_repository() -> QuotationRepository:
    global repository
    if repository is None:
        from src.core.config import get_settings

        settings = get_settings()
        if settings.storage_provider == "s3":
            if not settings.s3_bucket or not settings.s3_region:
                raise RuntimeError("S3_BUCKET và S3_REGION là bắt buộc khi STORAGE_PROVIDER=s3")
            storage: ObjectStorage = S3ObjectStorage(settings.s3_bucket, settings.s3_region, settings.s3_prefix)
        else:
            storage = FilesystemObjectStorage(settings.upload_dir)
        repository = (
            PostgresQuotationRepository(settings.database_url, storage)
            if settings.persistence_backend == "postgresql"
            else QuotationRepository(Path("data/quotations.json"), settings.upload_dir, storage)
        )
    return repository
