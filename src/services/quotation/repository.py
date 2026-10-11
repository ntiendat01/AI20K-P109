"""Kho quotation và file gốc cho MVP."""
# allow: SIZE_OK -- quotation metadata and its source-file lifecycle share persistence invariants.

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from src.models.quotation.confirmation import Quotation, QuotationConfirmation, QuotationStatus
from src.services.quotation.parser import ExtractedQuotation

logger = logging.getLogger(__name__)


def source_text(path: str) -> str:
    """Retain actual source text for audit; never reconstruct it from model output."""
    source = Path(path)
    try:
        if source.suffix.lower() == ".pdf":
            import pymupdf as fitz

            with fitz.open(source) as document:
                return "\n".join(page.get_text(sort=True) for page in document)
        return source.read_text(encoding="utf-8", errors="replace")
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
    def __init__(self, storage_path: Path, upload_root: Path) -> None:
        self.storage_path = storage_path
        self.upload_root = upload_root

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

        source_path = Path(quotation.source_path)
        if source_path.is_file() and not any(record.source_path == quotation.source_path for record in remaining):
            source_path.unlink()
        return quotation

    def delete_for_pr(self, pr_id: str) -> int:
        """Delete all quotations and their source files belonging to one PR."""
        quotations = self._load()
        targets = [quotation for quotation in quotations if quotation.pr_id == pr_id]

        # PR IDs are UUIDs created by this service; reject a path-shaped ID as
        # an extra guard before recursively deleting its dedicated upload folder.
        if Path(pr_id).name != pr_id:
            raise ValueError("Mã đề nghị mua không hợp lệ.")
        request_upload_dir = self.upload_root / pr_id
        if request_upload_dir.exists():
            shutil.rmtree(request_upload_dir)

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
        source_path = self.upload_root / pr_id / stored_filename
        source_path.parent.mkdir(parents=True, exist_ok=True)
        if not source_path.exists():
            try:
                source_path.write_bytes(content)
            except OSError:
                logger.exception(
                    "Quotation source could not be written",
                    extra={
                        "event": "quotation_source_write_failed",
                        "file_name": source_path.name,
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
            source_path=str(source_path),
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
                from src.services.quotation.intake import resume_confirmation

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
                        "source_text": source_text(quotation.source_path) or quotation.source_ocr_text or "",
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
                    }
                )
                records[i] = quote
                self._save(records)
                return quote
        return quote


repository = QuotationRepository(Path("data/quotations.json"), Path("data/uploads"))


def get_quotation_repository() -> QuotationRepository:
    return repository
