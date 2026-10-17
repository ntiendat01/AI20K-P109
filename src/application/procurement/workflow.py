"""Application bridge: confirmed quotations -> graph -> verified review -> durable PO."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from threading import RLock
from uuid import NAMESPACE_URL, uuid4, uuid5

from src.agents.graph import build_graph
from src.agents.nodes.decision_llm import DecisionModel
from src.application.evaluation.workflow import EvaluationWorkflow
from src.domain.agent.quotation.confirmation import (
    ConfirmedItemPayload,
    QuotationConfirmationRequest,
)
from src.domain.analysis.evaluation import (
    Actor,
    Chunk,
    Feedback,
    FeedbackReceipt,
    RuntimeEvaluationContext,
    SourceFact,
    SourceScope,
)
from src.domain.procurement.contracts import PurchaseOrder, PurchaseOrderItem, PurchaseRequest
from src.domain.quotation.confirmation import Quotation
from src.infrastructure.evaluation.evidence import content_hash
from src.infrastructure.evaluation.store import ReviewConflictError
from src.infrastructure.quotation.repository import QuotationRepository
from src.infrastructure.repositories.purchase_requests import PurchaseRequestRepository

MONEY_QUANTUM = Decimal("0.01")
logger = logging.getLogger(__name__)

REQUIRED_QUOTATION_FIELDS = (
    "vat_included",
    "vat_rate",
    "shipping_fee",
    "lead_time_days",
    "warranty_months",
)


def _json_payload(value: object) -> object:
    """Convert agent-contract/Pydantic values before storing a durable JSON snapshot."""
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if isinstance(value, list):
        return [_json_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_json_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_payload(item) for key, item in value.items()}
    return value


class MissingQuotationDataError(ValueError):
    """Structured, buyer-repairable input gap discovered before any agent call."""

    def __init__(self, missing_fields: list[dict[str, object]]) -> None:
        self.missing_fields = missing_fields
        super().__init__("Bổ sung các trường bắt buộc trên báo giá rồi chạy phân tích lại.")


@dataclass(frozen=True)
class AnalysisStart:
    """Prepared immutable input for the process-local background worker.

    ``run`` is persisted before this object is returned.  The remaining fields
    are deliberately kept in memory so an edit immediately after HTTP 202
    cannot change the snapshot a running graph evaluates.
    """

    run: dict
    state: dict | None = None
    context: RuntimeEvaluationContext | None = None
    chunks: list[Chunk] | None = None
    input_error: ValueError | None = None

    @property
    def should_execute(self) -> bool:
        return self.state is not None and self.context is not None and self.chunks is not None


def _missing_quotation_fields(quotes: list[Quotation]) -> list[dict[str, object]]:
    """Return all commercial gaps at once so the buyer can correct each supplier in one pass."""
    missing_by_supplier: list[dict[str, object]] = []
    for quote in quotes:
        fields = [field for field in REQUIRED_QUOTATION_FIELDS if getattr(quote, field) is None]
        if not quote.supplier_id:
            fields.append("supplier_id")
        if not quote.items:
            fields.append("items")
        if fields:
            missing_by_supplier.append(
                {
                    "supplier_id": quote.supplier_id or quote.id,
                    "supplier_name": quote.supplier_name,
                    "fields": fields,
                }
            )
    return missing_by_supplier


class ProcurementWorkflow:
    def __init__(
        self,
        path: Path,
        evaluation: EvaluationWorkflow,
        *,
        tenant_id: str,
        decision_model: DecisionModel | None = None,
        running_timeout_seconds: float = 300.0,
    ) -> None:
        self.path, self.evaluation, self.tenant_id = path, evaluation, tenant_id
        self.decision_model = decision_model
        self.running_timeout_seconds = running_timeout_seconds
        self.lock = RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS analysis (id TEXT PRIMARY KEY, pr_id TEXT, revision TEXT, data TEXT)"
            )
            db.execute("CREATE TABLE IF NOT EXISTS finalization (id TEXT PRIMARY KEY, data TEXT)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS evidence_cache (cache_key TEXT PRIMARY KEY, document_hash TEXT NOT NULL)"
            )

    def db(self):
        # Background graph workers and API polling use independent connections.
        # A finite timeout lets SQLite serialize a brief concurrent write instead
        # of failing an otherwise recoverable analysis with "database is locked".
        return sqlite3.connect(self.path, timeout=10)

    def migrate_legacy_runs(self, prs: PurchaseRequestRepository) -> int:
        """Fail closed for pre-evaluation runs without deleting their audit payloads."""
        migrated = 0
        with self.lock, self.db() as db:
            rows = db.execute("SELECT id, pr_id, data FROM analysis").fetchall()
            for analysis_id, pr_id, payload in rows:
                run = json.loads(payload)
                if run.get("status") not in {"untrusted_proposal", "awaiting_review"}:
                    continue
                run["status"] = "stale"
                run["message"] = "Đề xuất cũ chưa được kiểm chứng. Hãy phân tích lại trước khi gửi duyệt."
                db.execute(
                    "UPDATE analysis SET data=? WHERE id=?",
                    (json.dumps(run, ensure_ascii=False), analysis_id),
                )
                current = db.execute(
                    "SELECT id FROM analysis WHERE pr_id=? ORDER BY rowid DESC LIMIT 1", (pr_id,)
                ).fetchone()
                if current and current[0] == analysis_id:
                    prs.reset_stale_approval(pr_id, "Đề xuất cũ chưa được kiểm chứng; cần phân tích lại.")
                migrated += 1
        return migrated

    def actor(self, user, pr_ids: list[str]) -> Actor:
        return Actor(actor_id=user.id, tenant_id=self.tenant_id, roles=[user.role], case_ids=pr_ids)

    def save(self, run: dict) -> dict:
        with self.lock, self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO analysis VALUES (?,?,?,?)",
                (
                    run["analysis_id"],
                    run["pr_id"],
                    run["snapshot_revision"],
                    json.dumps(run, ensure_ascii=False),
                ),
            )
        return run

    def latest(self, pr_id: str) -> dict:
        with self.db() as db:
            rows = db.execute("SELECT rowid, data FROM analysis WHERE pr_id=?", (pr_id,)).fetchall()
        if not rows:
            return {"pr_id": pr_id, "status": "not_started"}
        # INSERT OR REPLACE moves a completed old run to the end of SQLite's
        # rowid order. Choose the immutable start timestamp for new runs so a
        # late worker cannot hide a newer snapshot. Pre-P3 records have no
        # timestamp; they must *not* be compared to it using their UUID, or a
        # UUID such as ``f...`` would permanently shadow a new ``2026-...`` run.
        parsed = [(rowid, json.loads(payload)) for rowid, payload in rows]
        timestamped = [
            (self._timestamp(run.get("started_at")), rowid, run)
            for rowid, run in parsed
            if self._timestamp(run.get("started_at")) is not None
        ]
        if timestamped:
            run = max(timestamped, key=lambda item: (item[0], item[1]))[2]
        else:
            run = max(parsed, key=lambda item: item[0])[1]
        return self._recover_expired_running(run)

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)

    def _recover_expired_running(self, run: dict) -> dict:
        if run.get("status") != "running":
            return run
        started_at = self._timestamp(run.get("started_at"))
        timed_out = started_at is None or (self._utc_now() - started_at).total_seconds() > self.running_timeout_seconds
        if not timed_out:
            return run
        recovered = {
            **run,
            "status": "technical_failure",
            "finished_at": self._utc_now().isoformat(),
            "message": "Phân tích chạy quá lâu hoặc bị gián đoạn. Hãy thử lại.",
        }
        self._log("analysis_recovered_timeout", recovered)
        return self.save(recovered)

    def _log(self, event: str, run: dict, **extra: object) -> None:
        """Emit correlation fields only; never serialize quotations or model output."""
        logger.info(
            json.dumps(
                {
                    "event": event,
                    "pr_id": run.get("pr_id"),
                    "analysis_id": run.get("analysis_id"),
                    "recommendation_id": run.get("recommendation_id"),
                    **extra,
                },
                ensure_ascii=False,
                default=str,
            )
        )

    def by_recommendation(self, recommendation_id: str) -> dict:
        with self.db() as db:
            rows = db.execute("SELECT data FROM analysis ORDER BY rowid DESC").fetchall()
        for row in rows:
            run = json.loads(row[0])
            if run.get("recommendation_id") == recommendation_id:
                return run
        raise ReviewConflictError("Không tìm thấy đề xuất của PR.")

    def by_analysis(self, analysis_id: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT data FROM analysis WHERE id=?", (analysis_id,)).fetchone()
        if row is None:
            raise ReviewConflictError("Analysis not found.")
        return json.loads(row[0])

    def audit_consistency(self, prs, pos) -> list[dict[str, str]]:
        """Report cross-store inconsistencies without mutating durable records."""
        del pos
        with self.db() as db:
            rows = db.execute("SELECT pr_id, data FROM analysis").fetchall()
        findings: list[dict[str, str]] = []
        for pr_id, payload in rows:
            run = json.loads(payload)
            if run.get("status") not in {"awaiting_review", "awaiting_buyer_review"}:
                continue
            if prs.get(pr_id) is None:
                findings.append(
                    {
                        "code": "AWAITING_REVIEW_WITHOUT_RECOMMENDATION",
                        "pr_id": pr_id,
                        "recommendation_id": run["recommendation_id"],
                    }
                )
        return findings

    def submit_buyer_review(self, analysis_id: str, user, note: str | None = None) -> dict:
        with self.lock:
            run = self.by_analysis(analysis_id)
            if run.get("status") != "awaiting_buyer_review":
                raise ReviewConflictError("Analysis is not awaiting Buyer confirmation.")
            run["buyer_confirmation"] = {
                "analysis_id": analysis_id,
                "analysis_revision": run["recommendation_version"],
                "submitted_by": user.id,
                "submitted_at": datetime.now().isoformat(),
                "note": note,
            }
            run["status"] = "pending_manager_approval"
            return self.save(run)

    def context(self, pr_id: str, actor: Actor) -> RuntimeEvaluationContext:
        run = self.latest(pr_id)
        context = RuntimeEvaluationContext.model_validate(run["context"])
        if actor.tenant_id != context.source_scope.tenant_id or pr_id not in actor.case_ids:
            raise ReviewConflictError("Không có quyền truy cập PR.")
        return context

    @staticmethod
    def _snapshot_payload(
        pr: PurchaseRequest, quotes: list[Quotation], *, as_of_date: str | None = None
    ) -> dict[str, object]:
        records = []
        for quote in sorted(quotes, key=lambda q: q.id):
            # ``source_path`` is an object key in production.  The upload
            # repository records this hash before persistence, so validation
            # does not rely on a container-local path.
            actual_hash = quote.source_hash or "missing"
            records.append(
                {**quote.model_dump(mode="json"), "file_hash": actual_hash, "audit": quote.confirmation_audit}
            )
        payload = {
            "pr": {
                "id": pr.id,
                # Quantity is a Decimal in the current PR contract.  Keep its
                # canonical string representation in the JSON snapshot so
                # starting an analysis never fails before the graph is queued.
                "requested_quantity": str(pr.requested_quantity),
                "requested_uom": pr.requested_uom,
                "target_currency": pr.target_currency,
                "budget": str(pr.estimated_budget),
                "deadline": pr.delivery_due_date.isoformat(),
                "metadata": (
                    {
                        "budget": str(pr.metadata.budget) if pr.metadata.budget is not None else None,
                        "delivery_time": pr.metadata.delivery_time.isoformat()
                        if pr.metadata.delivery_time is not None
                        else None,
                    }
                    if pr.metadata and (pr.metadata.budget is not None or pr.metadata.delivery_time is not None)
                    else None
                ),
                # Names, quantities, units and order determine matching and
                # TCO. Descriptive notes/category are level-0 labels and must
                # not make an otherwise valid analysis stale.
                "items": [
                    {
                        "id": item.item_id or f"{pr.id}:item:{index}",
                        "order_index": item.order_index,
                        "product_name": item.product_name,
                        "quantity": str(item.quantity),
                        "unit": item.unit,
                    }
                    for index, item in enumerate(sorted(pr.items, key=lambda row: row.order_index))
                ],
            },
            "quotes": records,
            "policy": "procurement-five-step-invalidation-v2",
        }
        # Calendar time is not a business input. Including it here made every
        # otherwise unchanged recommendation stale at midnight.
        if as_of_date is not None:
            payload["as_of_date"] = as_of_date
        return payload

    @classmethod
    def revision(cls, pr: PurchaseRequest, quotes: list[Quotation]) -> str:
        return content_hash(json.dumps(cls._snapshot_payload(pr, quotes), sort_keys=True, ensure_ascii=False))

    @classmethod
    def _legacy_revision(cls, pr: PurchaseRequest, quotes: list[Quotation], as_of_date: str) -> str:
        """Recreate the previous date-bound signature for a safe migration."""
        return content_hash(
            json.dumps(cls._snapshot_payload(pr, quotes, as_of_date=as_of_date), sort_keys=True, ensure_ascii=False)
        )

    @staticmethod
    def _legacy_as_of_dates(run: dict) -> set[str]:
        started_at = run.get("started_at")
        if not isinstance(started_at, str):
            return set()
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError:
            return set()
        # Old revisions used the server's local calendar date while started_at
        # is stored in UTC. Around midnight either neighbouring date is valid.
        return {(started + timedelta(days=offset)).date().isoformat() for offset in (-1, 0, 1)}

    def refresh_legacy_snapshot_revision(self, run: dict, pr: PurchaseRequest, quotes: list[Quotation]) -> dict:
        """Migrate a date-only legacy signature without masking real edits."""
        snapshot_revision = run.get("snapshot_revision")
        current_revision = self.revision(pr, quotes)
        if not isinstance(snapshot_revision, str) or snapshot_revision == current_revision:
            return run
        if not any(
            snapshot_revision == self._legacy_revision(pr, quotes, as_of_date)
            for as_of_date in self._legacy_as_of_dates(run)
        ):
            return run
        migrated = self.save({**run, "snapshot_revision": current_revision})
        self._log("analysis_snapshot_revision_migrated", migrated)
        return migrated

    def prepare(
        self, pr: PurchaseRequest, quotes: list[Quotation], rec_id: str
    ) -> tuple[dict, RuntimeEvaluationContext, list[Chunk]]:
        if len(quotes) < 2 or any(q.status != "confirmed" for q in quotes):
            raise ValueError("Cần ít nhất 2 báo giá đã xác nhận và không còn báo giá chờ đối soát.")
        names = [" ".join(q.supplier_name.casefold().split()) for q in quotes]
        if len(set(names)) != len(names) or len({q.supplier_id for q in quotes}) != len(quotes):
            raise ValueError("Mỗi nhà cung cấp chỉ dùng một báo giá cho lần phân tích; cần 2 NCC độc lập.")
        missing_fields = _missing_quotation_fields(quotes)
        if missing_fields:
            raise MissingQuotationDataError(missing_fields)
        raw, chunks, facts, plans, hashes, edits = [], [], [], [], {}, []
        confirmed_quotes: list[QuotationConfirmationRequest] = []
        confirmed_supplier_ids: list[str] = []
        target_uom = pr.requested_uom
        # A bundled quotation (for example, laptops, monitors and setup
        # services) legitimately has different units per line. Financial TCO
        # uses Buyer-confirmed line totals, so do not invent a conversion just
        # to force every line into the first line's UOM. Product reconciliation
        # remains the independent responsibility of fuzzy matching.
        preserve_line_item_uom = any(len(quote.items) > 1 for quote in quotes)
        for q in quotes:
            vat_included = q.vat_included
            vat_rate = q.vat_rate
            shipping_fee = q.shipping_fee
            lead_time_days = q.lead_time_days
            warranty_months = q.warranty_months

            # _missing_quotation_fields() establishes these before calculation.
            assert vat_included is not None
            assert vat_rate is not None
            assert shipping_fee is not None
            assert lead_time_days is not None
            assert warranty_months is not None

            factor = Decimal(1) if vat_included else Decimal(1) + vat_rate
            line_subtotal = sum((item.line_total for item in q.items), Decimal(0))
            goods = (line_subtotal * factor).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            shipping = (shipping_fee * factor).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            declared_total = (q.goods_total_including_tax or Decimal(0)) + (
                q.shipping_total_including_tax or Decimal(0)
            )
            aggregate_total = ((line_subtotal + shipping_fee) * factor).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            if (
                q.goods_total_including_tax is not None
                and q.shipping_total_including_tax is not None
                and declared_total != aggregate_total
            ):
                raise ValueError(
                    f"Tổng tiền đã xác nhận của {q.supplier_name} không khớp phép tính làm tròn. "
                    "Mở báo giá để kiểm tra lại VAT và phí giao hàng."
                )

            actual_source_hash = q.source_hash or "dummy_hash"
            supplier = q.supplier_id
            assert supplier is not None
            source_page = q.agent_extractions[0].get("source", {}).get("page_number") if q.agent_extractions else None
            original_id = f"{q.id}:original"

            audit = q.confirmation_audit or {}
            original_text = (
                audit.get("source_text") or f"Original document SHA256: {q.source_hash or actual_source_hash}"
            )
            hashes[q.id] = q.source_hash or actual_source_hash
            chunks.append(
                Chunk(
                    chunk_id=original_id,
                    text=original_text,
                    tenant_id=self.tenant_id,
                    case_id=pr.id,
                    document_id=q.id,
                    document_hash=hashes[q.id],
                    chunk_hash=content_hash(original_text),
                    source_kind="quotation",
                    supplier_id=supplier,
                    page=source_page,
                    block_id="original",
                )
            )
            edit_id = audit.get("audit_id") or str(uuid4())
            edits.append(edit_id)
            tco_val = goods + shipping

            specs = [
                ("tco", tco_val, "VND", "TCO", None),
                ("delivery_days", Decimal(lead_time_days), "calendar_day", "Delivery", "order_confirmation"),
                ("warranty_months", Decimal(warranty_months), "month", "Warranty", None),
            ]
            for metric, value, unit, label, origin in specs:
                unit_text = {"calendar_day": "calendar days", "month": "months"}.get(unit, unit)
                text = f"{label}: {value} {unit_text}" + (" after order confirmation." if origin else ".")
                cid = f"{q.id}:{edit_id}:{metric}"
                sf = SourceFact(
                    supplier_id=supplier,
                    metric=metric,
                    value=value,
                    unit=unit,
                    time_origin=origin,
                    value_text=str(value),
                    metric_text=label,
                    unit_text=unit_text,
                )
                chunks.append(
                    Chunk(
                        chunk_id=cid,
                        text=text,
                        tenant_id=self.tenant_id,
                        case_id=pr.id,
                        document_id=q.id,
                        document_hash=q.source_hash,
                        chunk_hash=content_hash(text),
                        source_kind="human_edit",
                        supplier_id=supplier,
                        page=source_page,
                        block_id=metric,
                        facts=[sf],
                        authenticated_edit_id=edit_id,
                        original_chunk_id=original_id,
                    )
                )
                facts.append(sf.model_dump(exclude={"value_text", "metric_text", "unit_text"}))

            for item_index, item in enumerate(q.items):
                raw.append(
                    {
                        "extraction_id": f"{q.id}:item-{item_index}",
                        "supplier_id": supplier,
                        "item_name": item.product_name,
                        "unit_price": float(item.unit_price),
                        "quantity": item.quantity,
                        "unit": item.unit,
                        "currency": pr.target_currency,
                        "vat_included": vat_included,
                        "vat_rate": float(vat_rate),
                        "surcharges": [
                            {
                                "kind": "shipping",
                                "description": "Buyer confirmed shipping",
                                "amount": float(shipping_fee),
                                "currency": "VND",
                            }
                        ],
                        "lead_time_days": lead_time_days,
                        "warranty_months": warranty_months,
                        "needs_confirmation": False,
                        "confirmed_by_human": True,
                        "source": {
                            "document_id": q.id,
                            "document_path": q.source_path,
                            "filename": q.source_filename,
                            "page_number": source_page,
                        },
                    }
                )
            # The agent graph uses strict agent contracts, whose confirmation
            # contract contains buyer-editable commercial values only.  Adapt
            # the legacy durable quotation at this boundary and carry the
            # server-owned supplier identity separately in graph state.
            confirmed_quotes.append(
                QuotationConfirmationRequest(
                    supplier_name=q.supplier_name,
                    currency=q.currency or "VND",
                    vat_rate=vat_rate,
                    vat_included=vat_included,
                    lead_time_days=lead_time_days,
                    warranty_months=warranty_months,
                    payment_terms=q.payment_terms.strip() or "Không nêu",
                    items=[
                        ConfirmedItemPayload(
                            source_item_id=f"{q.id}:item-{index}",
                            product_name=confirmed_item.product_name,
                            product_code=confirmed_item.product_code or None,
                            unit=confirmed_item.unit,
                            quantity=confirmed_item.quantity,
                            unit_price=confirmed_item.unit_price,
                        )
                        for index, confirmed_item in enumerate(q.items)
                    ],
                )
            )
            confirmed_supplier_ids.append(supplier)
        # Raw extractions contain one entry per quoted line, whereas the
        # evaluation context is supplier-scoped and requires unique candidates.
        candidates = confirmed_supplier_ids

        context = RuntimeEvaluationContext(
            case_id=pr.id,
            recommendation_id=rec_id,
            recommendation_version=1,
            candidate_ids=candidates,
            facts=facts,
            source_scope=SourceScope(tenant_id=self.tenant_id, case_id=pr.id, document_hashes=hashes),
            top_n=3,
            mandatory_comparisons=["tco", "delivery_days", "warranty_months"],
            constraints=[],
            calculations=plans,
            formula_allowlist=["sum_declared_tax_inclusive_components"],
            authorized_edit_ids=edits,
            approval_role="manager",
        )
        state = {
            "case_id": pr.id,
            "raw_extractions": raw,
            "confirmed_quotes": confirmed_quotes,
            "confirmed_supplier_ids": confirmed_supplier_ids,
            "pr_data": {
                "pr_number": pr.code,
                "quantity": pr.requested_quantity,
                "budget": float(pr.estimated_budget),
                "deadline": pr.delivery_due_date.isoformat(),
                "target_uom": target_uom,
                "target_currency": pr.target_currency,
                "top_n": 3,
                "preserve_line_item_uom": preserve_line_item_uom,
                "category": pr.category,
                "requested_uom": pr.requested_uom,
                "items": [
                    {
                        "id": item.item_id or f"{pr.id}:item-{index}",
                        "name": item.product_name,
                        "uom": item.unit,
                        "description": item.notes,
                    }
                    for index, item in enumerate(pr.items)
                ],
            },
            "decision_context": {
                "candidate_ids": candidates,
                "facts": [f.model_dump(mode="json") for f in context.facts],
                "constraints": [c.model_dump(mode="json") for c in context.constraints],
                "mandatory_comparisons": context.mandatory_comparisons,
            },
        }
        return state, context, chunks

    def start_analysis(self, pr: PurchaseRequest, quotes: list[Quotation], *, force: bool = False) -> AnalysisStart:
        """Validate and persist ``running`` before the graph is dispatched.

        The caller can safely return HTTP 202 once this method succeeds.  Input
        validation deliberately remains synchronous so a buyer gets a useful
        4xx response rather than an opaque background-task failure.
        """
        with self.lock:
            revision = self.revision(pr, quotes)
            old = self.refresh_legacy_snapshot_revision(self.latest(pr.id), pr, quotes)
            same_snapshot = old.get("snapshot_revision") == revision
            if same_snapshot and old.get("status") == "running":
                return AnalysisStart(old)
            if (
                not force
                and same_snapshot
                and old.get("status")
                in {
                    "awaiting_buyer_review",
                    "pending_manager_approval",
                    "approved",
                }
                # A pre-adapter run could reach the review interrupt with a
                # ``needs_input`` proposal and no calculable suppliers.  It is
                # not a reviewable cache entry; allow the repaired graph to run.
                and not (
                    old.get("status") == "awaiting_buyer_review"
                    and (old.get("review") or old.get("decision_proposal") or {}).get("status") == "needs_input"
                )
            ):
                return AnalysisStart(old)
            pending = old.get("pending_feedback")
            if pending and pending["revision_type"] != "explanation_change":
                return AnalysisStart(
                    self.save(
                        {
                            **old,
                            "status": "awaiting_input",
                            "message": "Đang chờ chủ sở hữu dữ liệu/ưu tiên/quy tắc áp dụng thay đổi. Chưa tạo đề xuất mới.",
                        }
                    )
                )
            rec_id = old["recommendation_id"] if pending else str(uuid4())
            version = self.evaluation.store.current(rec_id)["version"] + 1 if pending else 1
            started_at = self._utc_now().isoformat()
            run = {
                "analysis_id": str(uuid4()),
                "pr_id": pr.id,
                "recommendation_id": rec_id,
                "recommendation_version": version,
                "snapshot_revision": revision,
                "status": "running",
                "started_at": started_at,
                "events": [],
                "manager_note": old.get("manager_note"),
            }
            if pending:
                run["pending_feedback"] = pending
            try:
                state, context, chunks = self.prepare(pr, quotes, rec_id)
                context = context.model_copy(update={"recommendation_version": version})
                state["analysis_revision"] = version
                state.update(
                    analysis_id=run["analysis_id"],
                    recommendation_id=rec_id,
                    recommendation_version=version,
                )
                if pending:
                    state["decision_context"]["revision_request"] = pending["requested_changes"]
            except MissingQuotationDataError as exc:
                saved = self.save(
                    {
                        **run,
                        "status": "needs_input",
                        "finished_at": self._utc_now().isoformat(),
                        "message": str(exc),
                        "missing_fields": exc.missing_fields,
                    }
                )
                return AnalysisStart(saved, input_error=exc)
            except ValueError as exc:
                saved = self.save(
                    {**run, "status": "needs_input", "finished_at": self._utc_now().isoformat(), "message": str(exc)}
                )
                return AnalysisStart(saved, input_error=exc)
            run.update(
                supplier_names={q.supplier_id: q.supplier_name for q in quotes if q.supplier_id},
                context=context.model_dump(mode="json"),
                quotations=[
                    {**q.model_dump(mode="json"), "supplier_id": state["raw_extractions"][i]["supplier_id"]}
                    for i, q in enumerate(quotes)
                ],
            )
            saved = self.save(run)
            self._log("analysis_started", saved, force=force)
            return AnalysisStart(saved, state=state, context=context, chunks=chunks)

    def cancel_analysis(self, pr_id: str, analysis_id: str) -> dict:
        """Stop a running snapshot and prevent its worker from publishing a late result."""
        with self.lock:
            current = self.latest(pr_id)
            if current.get("analysis_id") != analysis_id:
                raise ValueError("Tiến trình phân tích đã thay đổi. Hãy tải lại trạng thái PR.")
            if current.get("status") != "running":
                return current
            cancelled = self.save({
                **current,
                "status": "stale",
                "finished_at": self._utc_now().isoformat(),
                "message": "Đã ngừng phân tích theo yêu cầu. Bạn có thể chỉnh sửa và chạy lại.",
            })
            self._log("analysis_cancelled", cancelled)
            return cancelled

    def _active_analysis(self, run: dict) -> bool:
        current = self.latest(run["pr_id"])
        return current.get("analysis_id") == run["analysis_id"] and current.get("status") == "running"

    def execute_analysis(self, start: AnalysisStart) -> dict:
        """Run a persisted analysis snapshot in the background worker."""
        if not start.should_execute:
            return start.run

        run, state = start.run, start.state
        assert state is not None
        if not self._active_analysis(run):
            return self.latest(run["pr_id"])
        try:
            assert start.chunks is not None
            self.evaluation.ingest_sources(start.chunks)
            if not self._active_analysis(run):
                return self.latest(run["pr_id"])
            graph = build_graph(confirmed_input=True, decision_model=self.decision_model)
            result: dict = {}
            waiting_for_buyer = False
            updates = iter(graph.stream(
                state, {"configurable": {"thread_id": run["analysis_id"]}}, stream_mode="updates"
            ))
            while self._active_analysis(run):
                try:
                    update = next(updates)
                except StopIteration:
                    break
                for node, output in update.items():
                    if node == "__interrupt__":
                        waiting_for_buyer = True
                        continue
                    # A LangGraph node that pauses for human review can emit a
                    # ``None`` update immediately before ``__interrupt__``.
                    # It carries no state and must not be merged into the
                    # accumulated analysis result.
                    if not isinstance(output, dict):
                        continue
                    result.update(output)
                    run["events"].append({"node": node, "at": self._utc_now().isoformat()})

            if not self._active_analysis(run):
                return self.latest(run["pr_id"])
            proposal = result.get("decision_proposal")
            proposal_payload = _json_payload(proposal) if proposal is not None else {}
            proposal_status = proposal_payload.get("status") if isinstance(proposal_payload, dict) else None
            normalization_issues: list[str] = []
            for artifact in result.get("normalized_quotes", []):
                artifact_payload = _json_payload(artifact)
                if isinstance(artifact_payload, dict):
                    normalization_issues.extend(str(issue) for issue in artifact_payload.get("issues", []))
            run_status = (
                "awaiting_buyer_review"
                if waiting_for_buyer and proposal_status == "proposed"
                else "needs_input"
                if proposal_status == "needs_input"
                else "needs_input"
                if normalization_issues
                else "technical_failure"
            )
            run.update(
                status=run_status,
                tco_results=_json_payload(result.get("tco_results", [])),
                comparison_matrix=_json_payload(result.get("comparison_matrix", {})),
                risk_flags=_json_payload(result.get("risk_flags", [])),
                decision_proposal=proposal_payload,
                review=proposal_payload if run_status == "awaiting_buyer_review" else None,
            )
            if run_status == "needs_input":
                run["message"] = proposal_payload.get(
                    "rationale",
                    "Chưa thể chuẩn hoá dữ liệu báo giá: " + "; ".join(normalization_issues),
                )
            elif run_status == "technical_failure":
                run["message"] = "Chưa gọi được model quyết định. Kiểm tra cấu hình provider và thử lại."
        except Exception as exc:
            logger.exception(
                "Procurement analysis failed",
                extra={
                    "event": "procurement_analysis_failed",
                    "error_type": type(exc).__name__,
                    "resource": "analysis",
                    "resource_id": run["analysis_id"],
                },
            )
            run.update(
                status="technical_failure",
                message="Phân tích thất bại. Kiểm tra provider/kho bằng chứng và thử lại.",
            )
        with self.lock:
            if not self._active_analysis(run):
                return self.latest(run["pr_id"])
            run["finished_at"] = self._utc_now().isoformat()
            saved = self.save(run)
        self._log("analysis_finished", saved, status=saved["status"])
        return saved

    def ensure_current(self, run: dict, prs: PurchaseRequestRepository, quotes: QuotationRepository) -> PurchaseRequest:
        pr = prs.get(run["pr_id"])
        if pr is None:
            raise ReviewConflictError("Dữ liệu PR/báo giá đã thay đổi. Hãy phân tích lại trước khi duyệt.")
        current_run = self.latest(run["pr_id"])
        if current_run.get("analysis_id") != run["analysis_id"]:
            raise ReviewConflictError("Đề xuất đã được thay thế. Hãy mở kết quả phân tích hiện hành.")
        current_run = self.refresh_legacy_snapshot_revision(current_run, pr, quotes.list_for_pr(pr.id))
        if self.revision(pr, quotes.list_for_pr(pr.id)) != current_run.get("snapshot_revision"):
            raise ReviewConflictError("Dữ liệu PR/báo giá đã thay đổi. Hãy phân tích lại trước khi duyệt.")
        # Callers can carry a deserialized legacy row. Keep that object in sync
        # so downstream approval/PO code persists the migrated revision too.
        run.clear()
        run.update(current_run)
        return pr

    def approval_command(self, run: dict, feedback: Feedback, user, pr: PurchaseRequest) -> dict:
        review = run.get("review") or {}
        selected = review.get("preferred_supplier_id")
        if not selected:
            raise ReviewConflictError("Đề xuất đã kiểm chứng không có nhà cung cấp được chọn.")
        quote = next((q for q in run["quotations"] if q["supplier_id"] == selected), None)
        if quote is None:
            raise ReviewConflictError("Nhà cung cấp đã kiểm chứng không thuộc snapshot báo giá hiện hành.")
        subtotal, shipping_amount, goods_total, shipping_total = self._po_amounts(quote)
        po_id = str(uuid5(NAMESPACE_URL, f"{feedback.recommendation_id}:{feedback.recommendation_version}"))
        po = PurchaseOrder(
            id=po_id,
            code=f"PO-{pr.code.removeprefix('PR-')}",
            pr_id=pr.id,
            pr_code=pr.code,
            quotation_id=quote["id"],
            supplier_name=quote["supplier_name"],
            items=[PurchaseOrderItem.model_validate(i) for i in quote["items"]],
            total_amount=goods_total + shipping_total,
            currency=quote["currency"],
            delivery_time=quote["delivery_time"],
            payment_terms=quote["payment_terms"],
            warranty=quote["warranty"],
            approver_id=user.id,
            approver_name=user.name,
            manager_note=feedback.note,
            subtotal=subtotal,
            shipping_amount=shipping_amount,
            tax_amount=goods_total + shipping_total - subtotal - shipping_amount,
            prices_include_tax=quote["vat_included"],
            recommendation_id=feedback.recommendation_id,
            recommendation_version=feedback.recommendation_version,
            snapshot_revision=run["snapshot_revision"],
        )
        return {"po": po.model_dump(mode="json"), "pr_id": pr.id}

    @staticmethod
    def _po_amounts(quote: dict) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """Return PO monetary amounts, deriving legacy confirmation totals when safe."""
        try:
            subtotal = sum((Decimal(str(item["line_total"])) for item in quote["items"]), Decimal("0"))
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise ReviewConflictError("Báo giá được chọn không có các dòng hàng hợp lệ để tạo PO.") from exc
        if subtotal <= 0:
            raise ReviewConflictError("Báo giá được chọn chưa có tổng dòng hàng hợp lệ để tạo PO.")

        vat_included = quote.get("vat_included")
        vat_rate = quote.get("vat_rate")
        shipping_amount = Decimal(str(quote.get("shipping_fee") or "0"))
        goods_value = quote.get("goods_total_including_tax")
        shipping_value = quote.get("shipping_total_including_tax")

        if goods_value is not None:
            goods_total = Decimal(str(goods_value))
        else:
            if vat_included is None or vat_rate is None:
                raise ReviewConflictError(
                    "Báo giá được chọn thiếu VAT hoặc tổng tiền. Mở lại báo giá, xác nhận VAT/phí rồi phân tích lại."
                )
            factor = Decimal("1") if vat_included else Decimal("1") + Decimal(str(vat_rate))
            goods_total = (subtotal * factor).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)

        if shipping_value is not None:
            shipping_total = Decimal(str(shipping_value))
        elif shipping_amount == 0:
            shipping_total = Decimal("0")
        else:
            if vat_included is None or vat_rate is None:
                raise ReviewConflictError(
                    "Báo giá được chọn thiếu VAT của phí vận chuyển. Mở lại báo giá, xác nhận VAT/phí rồi phân tích lại."
                )
            factor = Decimal("1") if vat_included else Decimal("1") + Decimal(str(vat_rate))
            shipping_total = (shipping_amount * factor).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)

        return subtotal, shipping_amount, goods_total, shipping_total

    def finalize(self, command: dict, prs, pos) -> PurchaseOrder:
        po = PurchaseOrder.model_validate(command["po"])
        pr_id = command.get("pr_id") or po.pr_id
        pr = prs.get(pr_id)
        if pr is None:
            raise ReviewConflictError("PR cần hoàn tất không còn tồn tại.")
        saved = pos.create(po)
        if pr.status != "approved":
            prs.approve(pr.id, saved.id)
        run = self.by_recommendation(po.recommendation_id)
        run["status"] = "approved"
        self.save(run)
        return saved

    def reconcile(self, prs, quotes, pos) -> int:
        """Replay approved durable commands after restart; never replay provider calls."""
        completed = 0
        with self.lock, self.db() as db:
            commands = db.execute("SELECT data FROM finalization").fetchall()
            for row in commands:
                command = json.loads(row[0])
                po = command["po"]
                recommendation_id = po["recommendation_id"]
                pr_id = command.get("pr_id") or po.get("pr_id")
                if not pr_id or prs.get(pr_id) is None:
                    logger.warning(
                        "Skipping finalization command for recommendation %s because its PR no longer exists.",
                        recommendation_id,
                    )
                    continue
                try:
                    current = self.evaluation.store.current(recommendation_id)
                except ReviewConflictError:
                    # A previous development run may have persisted a temporary
                    # untrusted-approval command without an evaluation record.
                    # It must not prevent the API from starting. Replay only when
                    # its durable analysis still authorizes the same command.
                    try:
                        run = self.by_recommendation(recommendation_id)
                    except ReviewConflictError:
                        logger.warning(
                            "Skipping orphaned finalization command for missing recommendation %s.",
                            recommendation_id,
                        )
                        continue
                    if run.get("status") not in {"pending_manager_approval", "approved"}:
                        logger.warning(
                            "Skipping finalization command for recommendation %s with status %s and no evaluation.",
                            recommendation_id,
                            run.get("status"),
                        )
                        continue
                    if self.latest(run["pr_id"]).get("analysis_id") != run["analysis_id"]:
                        continue
                    self.finalize(command, prs, pos)
                    completed += 1
                    continue
                if current["status"] != "approved" or current["version"] != po["recommendation_version"]:
                    continue
                run = self.by_recommendation(recommendation_id)
                # Approved snapshots are immutable; no provider or source retrieval is needed.
                if self.latest(run["pr_id"]).get("analysis_id") != run["analysis_id"]:
                    continue
                self.finalize(command, prs, pos)
                completed += 1
        return completed

    def feedback(self, feedback: Feedback, user, prs, quotes, pos) -> dict:
        with self.lock:
            if feedback.decision == "close":
                raise ReviewConflictError("Luồng PR hiện hỗ trợ approve/reject/revise; chưa có trạng thái đóng PR.")
            run = self.by_recommendation(feedback.recommendation_id)
            if run.get("status") in {"approved", "rejected"}:
                saved_feedback = run.get("manager_feedback")
                if (
                    isinstance(saved_feedback, dict)
                    and saved_feedback.get("idempotency_key") == feedback.idempotency_key
                ):
                    if saved_feedback != feedback.model_dump(mode="json"):
                        raise ReviewConflictError("Idempotency key conflicts with an earlier action")
                    response = {"receipt": run["manager_receipt"], "status": run["status"]}
                    if run["status"] == "approved":
                        command = self.approval_command(run, feedback, user, prs.get(run["pr_id"]))
                        response["po"] = command["po"]
                    return response
                raise ReviewConflictError("Đề xuất này đã được xử lý. Hãy tạo phân tích mới trước khi duyệt lại.")
            if run.get("status") == "pending_manager_approval":
                if not run.get("buyer_confirmation"):
                    raise ReviewConflictError("Thiếu xác nhận recommendation của Buyer.")
                if feedback.decision not in {"approve", "reject"}:
                    raise ReviewConflictError("Quản lý chỉ có thể phê duyệt hoặc từ chối đề xuất ở bước này.")
                if feedback.recommendation_version != run.get("recommendation_version"):
                    raise ReviewConflictError("Phiên bản đề xuất đã thay đổi. Hãy tải lại trước khi phê duyệt.")
                pr = self.ensure_current(run, prs, quotes)
                if pr.status != "pending_approval":
                    raise ReviewConflictError("PR chưa được gửi cho Quản lý phê duyệt.")
                if feedback.decision == "approve":
                    command = self.approval_command(run, feedback, user, pr)
                    po_id = command["po"]["id"]
                    with self.db() as db:
                        db.execute("INSERT OR REPLACE INTO finalization VALUES (?,?)", (po_id, json.dumps(command)))
                    receipt = FeedbackReceipt(
                        feedback_id=feedback.feedback_id,
                        recommendation_id=feedback.recommendation_id,
                        recommendation_version=feedback.recommendation_version,
                        state="applied",
                        workflow_status="approved",
                        route="MANAGER_APPROVAL_AFTER_BUYER_HITL",
                    )
                    po = self.finalize(command, prs, pos)
                    response = {
                        "receipt": receipt.model_dump(mode="json"),
                        "status": "approved",
                        "po": po.model_dump(mode="json"),
                    }
                    run["status"] = "approved"
                    run["manager_note"] = feedback.note
                    run["manager_feedback"] = feedback.model_dump(mode="json")
                    run["manager_receipt"] = response["receipt"]
                    self.save(run)
                    return response

                receipt = FeedbackReceipt(
                    feedback_id=feedback.feedback_id,
                    recommendation_id=feedback.recommendation_id,
                    recommendation_version=feedback.recommendation_version,
                    state="applied",
                    workflow_status="rejected",
                    route="MANAGER_REJECTION_AFTER_BUYER_HITL",
                )
                prs.reject(pr.id, feedback.note)
                run["manager_note"] = feedback.note
                run["manager_feedback"] = feedback.model_dump(mode="json")
                run["manager_receipt"] = receipt.model_dump(mode="json")
                run["status"] = receipt.workflow_status
                self.save(run)
                return {
                    "receipt": receipt.model_dump(mode="json"),
                    "status": receipt.workflow_status,
                }
            # A committed receipt replays its immutable PO even if the review date changes.
            current = self.evaluation.store.current(feedback.recommendation_id)
            pr = prs.get(run["pr_id"]) if current["status"] == "approved" else self.ensure_current(run, prs, quotes)
            if pr is None:
                raise ReviewConflictError("PR không còn tồn tại.")
            retryable = pr.status == "comparing" and run["status"] in {"rejected", "awaiting_input", "awaiting_repair"}
            if pr.status not in {"pending_approval", "approved"} and not retryable:
                raise ReviewConflictError("PR chưa được gửi cho Quản lý duyệt.")
            actor = self.actor(user, [pr.id])
            receipt = self.evaluation.feedback(feedback, actor)
            response = {"receipt": receipt.model_dump(mode="json"), "status": receipt.workflow_status}
            if receipt.workflow_status == "approved":
                command = self.approval_command(run, feedback, user, pr)
                po_id = command["po"]["id"]
                with self.db() as db:
                    db.execute("INSERT OR IGNORE INTO finalization VALUES (?,?)", (po_id, json.dumps(command)))
                with self.db() as db:
                    row = db.execute("SELECT data FROM finalization WHERE id=?", (po_id,)).fetchone()
                response["po"] = self.finalize(json.loads(row[0]), prs, pos).model_dump(mode="json")
            elif receipt.workflow_status == "rejected":
                if pr.status == "pending_approval":
                    prs.reject(pr.id, feedback.note)
            if feedback.decision == "revise":
                if pr.status == "pending_approval":
                    prs.reject(pr.id, feedback.note or "Yêu cầu cập nhật đề xuất")
                run["pending_feedback"] = feedback.model_dump(mode="json")
            if feedback.decision in {"reject", "revise"}:
                run["manager_note"] = feedback.note or feedback.requested_changes.explanation_change
            run["status"] = receipt.workflow_status
            self.save(run)
            return response
