import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.api.routes import procurement_workflow
from src.core.logging import JsonFormatter
from src.extraction.service import process_pdf
from src.models.purchase_request import PurchaseRequestCreate
from src.services.auth import DEMO_USERS
from src.services.evaluation.store import EvaluationStore
from src.services.procurement.purchase_requests import PurchaseRequestRepository
from src.services.quotation.parser import ExtractedQuotation
from src.services.quotation.repository import QuotationRepository, source_text


def test_structured_formatter_includes_operational_fields():
    # Given
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "event happened", (), None)
    record.event = "pr_created"
    record.resource_id = "pr-123"

    # When
    payload = json.loads(JsonFormatter().format(record))

    # Then
    assert payload["event"] == "pr_created"
    assert payload["resource_id"] == "pr-123"
    assert "client_ip" not in payload


def test_transaction_rollback_is_logged(tmp_path, caplog):
    # Given
    store = EvaluationStore(tmp_path / "evaluation.sqlite3")
    caplog.set_level(logging.WARNING)
    caplog.clear()

    # When
    with pytest.raises(OSError), store.transaction():
        raise OSError("force rollback")

    # Then
    rollback_logs = [
        record for record in caplog.records if getattr(record, "event", None) == "database_transaction_rolled_back"
    ]
    assert len(rollback_logs) == 1
    assert rollback_logs[0].storage_backend == "sqlite"
    assert rollback_logs[0].error_type == "OSError"


def test_database_connection_failure_is_logged(monkeypatch, tmp_path, caplog):
    # Given
    def fail_to_connect(*args, **kwargs):
        del args, kwargs
        raise store_module.sqlite3.OperationalError("database unavailable")

    from src.services.evaluation import store as store_module

    monkeypatch.setattr(store_module.sqlite3, "connect", fail_to_connect)
    caplog.set_level(logging.ERROR)

    # When
    with pytest.raises(store_module.sqlite3.OperationalError):
        EvaluationStore(tmp_path / "evaluation.sqlite3")

    # Then
    failure_logs = [
        record for record in caplog.records if getattr(record, "event", None) == "database_connection_failed"
    ]
    assert len(failure_logs) == 1
    assert failure_logs[0].storage_backend == "sqlite"


def test_corrupt_pdf_failure_is_logged(caplog):
    # Given
    caplog.set_level(logging.WARNING)

    # When
    result = process_pdf("broken.pdf", b"not-a-pdf")

    # Then
    failure_logs = [record for record in caplog.records if getattr(record, "event", None) == "pdf_extraction_failed"]
    assert result.status == "failed"
    assert len(failure_logs) == 1
    assert failure_logs[0].file_name == "broken.pdf"


def test_missing_quotation_source_is_logged(tmp_path, caplog):
    # Given
    missing_file = tmp_path / "missing.pdf"
    caplog.set_level(logging.WARNING)

    # When
    content = source_text(str(missing_file))

    # Then
    failure_logs = [
        record for record in caplog.records if getattr(record, "event", None) == "quotation_source_read_failed"
    ]
    assert content == ""
    assert len(failure_logs) == 1
    assert failure_logs[0].file_name == "missing.pdf"


def test_quotation_source_write_failure_is_logged(monkeypatch, tmp_path, caplog):
    # Given
    repository = QuotationRepository(tmp_path / "quotations.json", tmp_path / "uploads")

    def fail_to_write(self, content):
        del self, content
        raise OSError("disk unavailable")

    monkeypatch.setattr(Path, "write_bytes", fail_to_write)
    caplog.set_level(logging.ERROR)

    # When
    with pytest.raises(OSError):
        repository.save_upload(
            pr_id="pr-123",
            supplier_name="Supplier",
            source_filename="quote.pdf",
            source_content_type="application/pdf",
            content=b"%PDF-1.7",
            extracted=ExtractedQuotation(),
            cache_hit=False,
            extraction_version=1,
        )

    # Then
    failure_logs = [
        record for record in caplog.records if getattr(record, "event", None) == "quotation_source_write_failed"
    ]
    assert len(failure_logs) == 1
    assert failure_logs[0].resource_id == "pr-123"


def test_chromadb_initialization_failure_is_logged(monkeypatch, caplog):
    # Given
    def fail_to_connect(*args, **kwargs):
        del args, kwargs
        raise OSError("chroma unavailable")

    monkeypatch.setattr(procurement_workflow.chromadb, "PersistentClient", fail_to_connect)
    caplog.set_level(logging.ERROR)

    # When
    with pytest.raises(OSError):
        procurement_workflow.initialize_procurement(SimpleNamespace(state=SimpleNamespace()))

    # Then
    failure_logs = [
        record for record in caplog.records if getattr(record, "event", None) == "vector_database_connection_failed"
    ]
    assert len(failure_logs) == 1
    assert failure_logs[0].storage_backend == "chromadb"


def purchase_request_payload(code: str) -> PurchaseRequestCreate:
    return PurchaseRequestCreate(
        code=code,
        category="Laboratory equipment",
        requested_quantity=1,
        requested_uom="cái",
        target_currency="VND",
        estimated_budget=Decimal("1000000"),
        delivery_due_date=date.today() + timedelta(days=7),
    )


def test_purchase_request_approval_transition_is_logged(tmp_path, caplog):
    # Given
    repository = PurchaseRequestRepository(tmp_path / "purchase_requests.json")
    request = repository.create(purchase_request_payload("PR-APPROVE-001"), DEMO_USERS[0])
    repository.register_quotation(request.id)
    repository.submit_for_approval(request.id)
    caplog.set_level(logging.INFO)
    caplog.clear()

    # When
    approved = repository.approve(request.id, "po-123")

    # Then
    audit_logs = [record for record in caplog.records if getattr(record, "event", None) == "pr_approved"]
    assert approved is not None
    assert len(audit_logs) == 1
    assert audit_logs[0].previous_status == "pending_approval"
    assert audit_logs[0].new_status == "approved"


def test_purchase_request_rejection_transition_is_logged(tmp_path, caplog):
    # Given
    repository = PurchaseRequestRepository(tmp_path / "purchase_requests.json")
    request = repository.create(purchase_request_payload("PR-REJECT-001"), DEMO_USERS[0])
    repository.register_quotation(request.id)
    repository.submit_for_approval(request.id)
    caplog.set_level(logging.INFO)
    caplog.clear()

    # When
    rejected = repository.reject(request.id, "Revise supplier selection")

    # Then
    audit_logs = [record for record in caplog.records if getattr(record, "event", None) == "pr_rejected"]
    assert rejected is not None
    assert len(audit_logs) == 1
    assert audit_logs[0].previous_status == "pending_approval"
    assert audit_logs[0].new_status == "comparing"
