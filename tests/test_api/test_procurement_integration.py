"""Real graph, Chroma and review persistence, with only decision provider faked."""

import asyncio
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from src.main import app
from src.services.procurement.workflow import ProcurementWorkflow


async def login(client, role):
    r = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "purchasing@vinuni.edu.vn" if role == "procurement" else "manager@vinuni.edu.vn",
            "password": "Purchase123!" if role == "procurement" else "Manager123!",
        },
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def prepare(client):
    buyer = await login(client, "procurement")
    manager = await login(client, "manager")
    r = await client.post(
        "/api/v1/prs",
        headers=buyer,
        json={
            "code": "PR-INTEGRATION",
            "category": "Anonymous Widget",
            "quantity": 10,
            "estimated_budget": "20000",
            "delivery_due_date": (date.today() + timedelta(days=30)).isoformat(),
        },
    )
    assert r.status_code == 201
    pr_id = r.json()["id"]
    for name, price, days, warranty in [("Vendor A", 1000, 5, 12), ("Vendor B", 1200, 7, 24)]:
        text = f"Supplier: {name}\nDelivery: {days} days\nItem | Quantity | Unit price | Amount\nWidget | 10 | {price} | {price * 10}"
        r = await client.post(
            f"/api/v1/prs/{pr_id}/quotations",
            headers=buyer,
            files={"file": (f"{name}.txt", text.encode(), "text/plain")},
        )
        assert r.status_code == 201
        qid = r.json()["id"]
        r = await client.post(
            f"/api/v1/quotations/{qid}/confirm",
            headers=buyer,
            json={
                "supplier_name": name,
                "delivery_time": f"{days} ngày lịch",
                "currency": "VND",
                "payment_terms": "Sau nghiệm thu",
                "vat_rate": "0.1",
                "vat_included": False,
                "shipping_fee": "0",
                "lead_time_days": days,
                "warranty_months": warranty,
                "goods_total_including_tax": str(price * 11),
                "shipping_total_including_tax": "0",
                "items": [
                    {
                        "product_name": "Widget",
                        "unit": "cái",
                        "quantity": 10,
                        "unit_price": price,
                        "line_total": price * 10,
                    }
                ],
            },
        )
        assert r.status_code == 200, r.text
    return pr_id, buyer, manager


async def completed_analysis(client, pr_id, buyer, *, force=False):
    """Start the API's async analysis and poll it as the browser does."""
    suffix = "?force=true" if force else ""
    started = await client.post(f"/api/v1/prs/{pr_id}/analysis{suffix}", headers=buyer)
    assert started.status_code in {200, 202}, started.text
    run = started.json()
    for _ in range(200):
        if run["status"] != "running":
            return run
        await asyncio.sleep(0.01)
        response = await client.get(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)
        assert response.status_code == 200, response.text
        run = response.json()
    raise AssertionError("analysis did not reach a terminal state")


@pytest.mark.asyncio
async def test_manager_can_reject_submitted_recommendation_without_creating_a_po(client, integration):
    service, prs, _, pos, _ = integration
    pr_id, buyer, manager = await prepare(client)
    run = await completed_analysis(client, pr_id, buyer)
    assert run["status"] == "awaiting_buyer_review", run

    submitted = await client.post(
        f"/api/v1/analyses/{run['analysis_id']}/submit-approval",
        headers=buyer,
        json={},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_manager_approval"

    payload = {
        "feedback_id": "manager-reject",
        "idempotency_key": "manager-reject",
        "recommendation_id": run["recommendation_id"],
        "recommendation_version": run["recommendation_version"],
        "decision": "reject",
        "note": "Cần thương lượng lại điều khoản trước khi phê duyệt.",
    }
    path = f"/api/v1/recommendations/{run['recommendation_id']}/feedback"
    response = await client.post(path, headers=manager, json=payload)
    retry = await client.post(path, headers=manager, json=payload)

    assert response.status_code == retry.status_code == 200, response.text
    assert response.json()["status"] == "rejected"
    assert prs.get(pr_id).status == "comparing"
    assert prs.get(pr_id).rejection_reason == payload["note"]
    assert service.latest(pr_id)["status"] == "rejected"
    assert service.latest(pr_id)["manager_note"] == payload["note"]
    assert pos.list() == []

    workspace = await client.get("/api/v1/prs", headers=buyer)
    detail = await client.get(f"/api/v1/prs/{pr_id}", headers=buyer)
    assert workspace.status_code == detail.status_code == 200
    assert next(item for item in workspace.json() if item["id"] == pr_id)["rejection_reason"] == payload["note"]
    assert detail.json()["rejection_reason"] == payload["note"]

    # A later Buyer submission is a new review cycle, so the old alert must clear.
    assert prs.submit_for_approval(pr_id).rejection_reason is None


@pytest.mark.asyncio
async def test_prepare_projects_legacy_confirmations_into_v1_analysis_state(client, integration):
    """The v1 graph must receive confirmed quotes, not only legacy raw rows."""
    service, prs, quotes, _, _ = integration
    pr_id, _, _ = await prepare(client)

    state, _, _ = service.prepare(prs.get(pr_id), quotes.list_for_pr(pr_id), "recommendation-v1")

    assert len(state["confirmed_quotes"]) == 2
    assert state["confirmed_supplier_ids"] == [quote.supplier_id for quote in quotes.list_for_pr(pr_id)]

    from src.agents.nodes.analysis_tools import calculate_tco_node
    from src.agents.nodes.normalize import normalize

    state.update(normalize(state))
    state.update(calculate_tco_node(state))

    assert [result.supplier_id for result in state["tco_results"]] == state["confirmed_supplier_ids"]
    assert sorted(result.total_tco for result in state["tco_results"]) == [Decimal("11000.00"), Decimal("13200.00")]


@pytest.mark.asyncio
async def test_needs_input_proposal_is_not_mislabelled_as_buyer_review(client, integration, monkeypatch):
    """A decision with no eligible supplier must remain repairable, not reviewable."""
    service, prs, quotes, _, _ = integration
    pr_id, _, _ = await prepare(client)
    start = service.start_analysis(prs.get(pr_id), quotes.list_for_pr(pr_id))

    class NeedsInputGraph:
        def stream(self, state, config, stream_mode):
            del state, config, stream_mode
            yield {"decision_llm": {"decision_proposal": {"status": "needs_input", "rationale": "Thiếu TCO."}}}

    monkeypatch.setattr("src.services.procurement.workflow.build_graph", lambda **_: NeedsInputGraph())

    result = service.execute_analysis(start)

    assert result["status"] == "needs_input"
    assert result["message"] == "Thiếu TCO."
    assert result["review"] is None


@pytest.mark.asyncio
async def test_unmapped_unit_is_explained_without_a_fake_model_failure(client, integration, monkeypatch):
    """A graph that stops at normalization must give the Buyer the real reason."""
    service, prs, quotes, _, _ = integration
    pr_id, _, _ = await prepare(client)
    start = service.start_analysis(prs.get(pr_id), quotes.list_for_pr(pr_id))

    class NormalizeOnlyGraph:
        def stream(self, state, config, stream_mode):
            del state, config, stream_mode
            yield {
                "normalize": {
                    "normalized_quotes": [{"status": "needs_mapping", "issues": ["missing UOM mapping 'MT' -> 'tấn'"]}]
                }
            }

    monkeypatch.setattr("src.services.procurement.workflow.build_graph", lambda **_: NormalizeOnlyGraph())

    result = service.execute_analysis(start)

    assert result["status"] == "needs_input"
    assert "missing UOM mapping 'MT' -> 'tấn'" in result["message"]


@pytest.mark.asyncio
async def test_happy_path_graph_evidence_review_po_and_retry(client, integration):
    service, prs, quotes, pos, model = integration
    pr_id, buyer, manager = await prepare(client)
    run = await completed_analysis(client, pr_id, buyer)
    assert run["status"] == "awaiting_buyer_review", run
    assert {event["node"] for event in run["events"]} == {
        "normalize",
        "calculate_tco",
        "analyze_risks",
        "compare_suppliers",
        "decision_llm",
    }
    assert sorted(t["total_tco"] for t in run["tco_results"]) == [11000, 13200]
    assert run["decision_proposal"]["status"] == "proposed"
    assert model.calls == 1
    from tests.fixtures.procurement_integration import integration_service

    cold = integration_service(service.path.parent)
    assert cold.latest(pr_id)["analysis_id"] == run["analysis_id"]
    assert cold.decision_model.calls == 0
    assert (await completed_analysis(client, pr_id, buyer))["analysis_id"] == run["analysis_id"]
    assert model.calls == 1
    assert (
        await client.post(f"/api/v1/analyses/{run['analysis_id']}/submit-approval", headers=buyer, json={})
    ).status_code == 200
    review = await client.get(f"/api/v1/recommendations/{run['recommendation_id']}/review", headers=manager)
    assert review.status_code == 200
    q = quotes.list_for_pr(pr_id)[0]
    source = await client.get(f"/api/v1/recommendations/{run['recommendation_id']}/sources/{q.id}", headers=manager)
    assert source.status_code == 200 and source.content == Path(q.source_path).read_bytes()
    wrong_source = await client.get(
        f"/api/v1/recommendations/{run['recommendation_id']}/sources/unrelated", headers=manager
    )
    assert wrong_source.status_code == 404
    payload = {
        "feedback_id": "happy-click",
        "idempotency_key": "happy-click",
        "decision": "approve",
        "recommendation_id": run["recommendation_id"],
        "recommendation_version": 1,
        "note": "Đồng ý",
    }
    path = f"/api/v1/recommendations/{run['recommendation_id']}/feedback"
    assert (await client.post(path, headers=buyer, json=payload)).status_code == 403
    first = await client.post(path, headers=manager, json=payload)
    retry = await client.post(path, headers=manager, json=payload)
    assert first.status_code == retry.status_code == 200, first.text
    assert first.json()["po"]["id"] == retry.json()["po"]["id"]
    po = first.json()["po"]
    assert po["supplier_name"] == "Vendor A"
    assert float(po["total_amount"]) == 11000
    assert float(po["subtotal"]) == 10000 and float(po["tax_amount"]) == 1000
    assert float(po["shipping_amount"]) == 0
    assert po["recommendation_id"] == run["recommendation_id"]
    assert po["snapshot_revision"] == run["snapshot_revision"]
    assert prs.get(pr_id).po_id == po["id"]
    assert len(pos.list()) == 1
    assert first.json()["receipt"]["route"] == "MANAGER_APPROVAL_AFTER_BUYER_HITL"
    assert (await client.delete(f"/api/v1/prs/{pr_id}", headers=buyer)).status_code == 409
    assert prs.get(pr_id) is not None and Path(quotes.list_for_pr(pr_id)[0].source_path).is_file()
    restarted = ProcurementWorkflow(service.path, service.evaluation, tenant_id="test", decision_model=model)
    assert restarted.latest(pr_id)["status"] == "approved"


@pytest.mark.asyncio
async def test_stale_source_and_missing_analysis_cannot_approve(client, integration):
    service, prs, quotes, pos, _ = integration
    pr_id, buyer, manager = await prepare(client)
    assert (await client.post("/api/v1/analyses/missing/submit-approval", headers=buyer, json={})).status_code == 409
    run = await completed_analysis(client, pr_id, buyer)
    assert run["status"] == "awaiting_buyer_review", run
    assert (
        await client.post(f"/api/v1/analyses/{run['analysis_id']}/submit-approval", headers=buyer, json={})
    ).status_code == 200
    Path(quotes.list_for_pr(pr_id)[0].source_path).write_text("tampered")
    assert (
        await client.post(f"/api/v1/recommendations/{run['recommendation_id']}/feedback", headers=manager, json={})
    ).status_code == 422
    assert not pos.list()


@pytest.mark.asyncio
async def test_agent_pdf_intake_requires_confirmation_and_survives_restart(client, integration, monkeypatch):
    import fitz

    from src.services.quotation.intake import TextFirstOCR
    from src.services.quotation.repository import QuotationRepository

    service, prs, quotes, pos, model = integration
    buyer, manager = await login(client, "procurement"), await login(client, "manager")
    created = await client.post(
        "/api/v1/prs",
        headers=buyer,
        json={
            "code": "PR-PDF-AGENT",
            "category": "Anonymous Widget",
            "quantity": 10,
            "estimated_budget": "20000",
            "delivery_due_date": (date.today() + timedelta(days=30)).isoformat(),
        },
    )
    assert created.status_code == 201
    pr_id = created.json()["id"]

    class OCR:
        calls = 0

        def extract_text(self, path):
            self.calls += 1
            return TextFirstOCR().extract_text(path)

    class Extraction:
        calls = 0

        def extract_items(self, text, path):
            self.calls += 1
            is_a = "Vendor A" in text
            return [
                {
                    "supplier": "Vendor A" if is_a else "Vendor B",
                    "item_name": "Widget",
                    "unit_price": 900 if is_a else 1200,
                    "quantity": 10,
                    "unit": "cái",
                    "currency": "VND",
                    "vat_rate": 0.1,
                    "vat_included": False,
                    "shipping_fee": 0,
                    "lead_time_days": 4 if is_a else 7,
                    "warranty_months": 6 if is_a else 24,
                    "page_number": 1,
                    "confidence_score": 0.5,
                    "source_text": "",
                }
            ]

    ocr, extractor = OCR(), Extraction()
    monkeypatch.setattr(app.state, "intake_ocr", ocr, raising=False)
    monkeypatch.setattr(app.state, "intake_extractor", extractor, raising=False)
    pending = []
    for name in ["Vendor A", "Vendor B"]:
        with fitz.open() as pdf:
            pdf.new_page().insert_text(
                (72, 72), f"Supplier: {name}\nWidget quantity 10. Unit price {1000 if name == 'Vendor A' else 1200} VND"
            )
            content = pdf.tobytes()
        uploaded = await client.post(
            f"/api/v1/prs/{pr_id}/quotations",
            headers=buyer,
            data={"extraction_mode": "agent"},
            files={"file": (f"{name}.pdf", content, "application/pdf")},
        )
        assert uploaded.status_code == 201, uploaded.text
        quote = uploaded.json()
        assert quote["status"] == "unconfirmed"
        assert quote["extraction_mode"] == "agent"
        assert quote["agent_extractions"][0]["confirmed_by_human"] is False
        pending.append(quote)
    blocked = await client.post(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)
    assert blocked.status_code == 422
    assert (await client.get(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)).json()["status"] == "needs_input"
    assert model.calls == 0
    # Rebuild repository after the interrupted extraction: resume uses durable rows.
    restarted_quotes = QuotationRepository(quotes.storage_path, quotes.upload_root)
    assert restarted_quotes.get(pending[0]["id"]).items[0].unit_price == 900
    assert "Vendor A" in restarted_quotes.get(pending[0]["id"]).source_ocr_text
    assert "source_ocr_text" not in pending[0]
    from src.services.quotation.repository import get_quotation_repository

    app.dependency_overrides[get_quotation_repository] = lambda: restarted_quotes
    for quote in pending:
        is_a = quote["supplier_name"] == "Vendor A"
        price = 1000 if is_a else 1200
        payload = {
            "supplier_name": quote["supplier_name"],
            "currency": "VND",
            "vat_rate": "0.1",
            "vat_included": False,
            "shipping_fee": "0",
            "lead_time_days": 5 if is_a else 7,
            "warranty_months": 12 if is_a else 24,
            "goods_total_including_tax": str(price * 11),
            "shipping_total_including_tax": "0",
            "items": [
                {"product_name": "Widget", "quantity": 10, "unit": "cái", "unit_price": price, "line_total": price * 10}
            ],
        }
        path = f"/api/v1/quotations/{quote['id']}/confirm"
        assert (await client.post(path, headers=manager, json=payload)).status_code == 403
        confirmed = await client.post(path, headers=buyer, json=payload)
        assert confirmed.status_code == 200, confirmed.text
        raw = confirmed.json()["agent_extractions"][0]
        assert raw["confirmed_by_human"] is True and raw["needs_confirmation"] is False
        assert raw["unit_price"] == price
        assert raw["lead_time_days"] == (5 if is_a else 7)
        assert raw["warranty_months"] == (12 if is_a else 24)
        assert raw["extraction_id"] == quote["agent_extractions"][0]["extraction_id"]
    assert ocr.calls == extractor.calls == 2
    run = await completed_analysis(client, pr_id, buyer)
    assert run["status"] == "awaiting_buyer_review", run
    assert sorted(t["total_tco"] for t in run["tco_results"]) == [11000, 13200]
    assert ocr.calls == extractor.calls == 2
    assert (
        await client.post(f"/api/v1/analyses/{run['analysis_id']}/submit-approval", headers=buyer, json={})
    ).status_code == 200
    approved = await client.post(
        f"/api/v1/recommendations/{run['recommendation_id']}/feedback",
        headers=manager,
        json={
            "feedback_id": "pdf-intake-approval",
            "idempotency_key": "pdf-intake-approval",
            "recommendation_id": run["recommendation_id"],
            "recommendation_version": run["recommendation_version"],
            "decision": "approve",
        },
    )
    assert approved.status_code == 200, approved.text
    assert float(approved.json()["po"]["total_amount"]) == 11000
    assert len(pos.list()) == 1


@pytest.mark.asyncio
async def test_restart_reconciles_approval_when_po_write_fails(client, integration, monkeypatch):
    from src.services.procurement.workflow import ProcurementWorkflow

    service, prs, quotes, pos, model = integration
    pr_id, buyer, manager = await prepare(client)
    run = await completed_analysis(client, pr_id, buyer)
    assert run["status"] == "awaiting_buyer_review"
    assert (
        await client.post(f"/api/v1/analyses/{run['analysis_id']}/submit-approval", headers=buyer, json={})
    ).status_code == 200
    original_create = pos.create

    def unavailable(po):
        raise OSError("Simulated disk write failure")

    monkeypatch.setattr(pos, "create", unavailable)
    payload = {
        "feedback_id": "crash-click",
        "idempotency_key": "crash-click",
        "decision": "approve",
        "recommendation_id": run["recommendation_id"],
        "recommendation_version": 1,
    }
    from src.services.auth import get_session

    user = get_session(manager["Authorization"].removeprefix("Bearer ")).user
    from src.models.evaluation import Feedback

    with pytest.raises(OSError):
        service.feedback(Feedback.model_validate(payload), user, prs, quotes, pos)
    assert service.latest(pr_id)["status"] == "pending_manager_approval"
    assert not pos.list()
    monkeypatch.setattr(pos, "create", original_create)
    restarted = ProcurementWorkflow(service.path, service.evaluation, tenant_id="test", decision_model=model)
    assert restarted.reconcile(prs, quotes, pos) == 1
    assert restarted.latest(pr_id)["status"] == "approved"
    assert prs.get(pr_id).po_id == pos.list()[0].id
    restarted.reconcile(prs, quotes, pos)
    assert len(pos.list()) == 1 and model.calls == 1


def test_reconcile_skips_orphaned_finalization_command(integration):
    """Old durable commands must not prevent application startup after data reset."""
    service, prs, quotes, pos, _ = integration
    with service.db() as db:
        db.execute(
            "INSERT INTO finalization VALUES (?,?)",
            (
                "orphaned-po",
                json.dumps({"po": {"recommendation_id": "missing", "recommendation_version": 1}}),
            ),
        )

    assert service.reconcile(prs, quotes, pos) == 0


def test_po_amounts_derive_missing_legacy_confirmation_totals():
    subtotal, shipping, goods_total, shipping_total = ProcurementWorkflow._po_amounts(
        {
            "items": [{"line_total": "100"}],
            "vat_included": False,
            "vat_rate": "0.08",
            "shipping_fee": None,
            "goods_total_including_tax": None,
            "shipping_total_including_tax": None,
        }
    )

    assert (subtotal, shipping, goods_total, shipping_total) == (
        Decimal("100"),
        Decimal("0"),
        Decimal("108.00"),
        Decimal("0"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    ["vat_included", "vat_rate", "shipping_fee", "lead_time_days", "warranty_months"],
)
async def test_legacy_missing_quotation_field_never_calls_model(client, integration, field):
    service, prs, quotes, pos, model = integration
    pr_id, buyer, manager = await prepare(client)
    records = quotes._load()
    records[0] = records[0].model_copy(update={field: None})
    quotes._save(records)
    response = await client.post(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)
    assert response.status_code == 422
    run = (await client.get(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)).json()
    assert run["status"] == "needs_input" and model.calls == 0
    assert run["missing_fields"] == [
        {"supplier_id": records[0].supplier_id, "supplier_name": "Vendor A", "fields": [field]}
    ]
    assert not pos.list()


@pytest.mark.asyncio
async def test_corrected_quotation_clears_a_stale_missing_data_run_and_can_be_reanalyzed(client, integration):
    service, _, quotes, _, model = integration
    pr_id, buyer, _ = await prepare(client)
    records = quotes._load()
    records[0] = records[0].model_copy(update={"lead_time_days": None})
    quotes._save(records)

    blocked_response = await client.post(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)
    assert blocked_response.status_code == 422
    blocked = (await client.get(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)).json()
    assert blocked["status"] == "needs_input"
    assert blocked["missing_fields"][0]["fields"] == ["lead_time_days"]
    assert model.calls == 0

    records[0] = records[0].model_copy(update={"lead_time_days": 6})
    quotes._save(records)
    refreshed = await client.get(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)

    assert refreshed.status_code == 200
    stale = refreshed.json()
    assert stale["status"] == "stale"
    assert stale["missing_fields"] == []
    assert stale["message"] == "Dữ liệu PR hoặc báo giá đã thay đổi. Hãy chạy lại phân tích."

    rerun = await completed_analysis(client, pr_id, buyer)
    assert rerun["status"] == "awaiting_buyer_review"
    assert model.calls == 1


@pytest.mark.asyncio
async def test_date_only_legacy_snapshot_is_migrated_without_invalidating_the_review(client, integration):
    service, prs, quotes, _, _ = integration
    pr_id, buyer, _ = await prepare(client)
    completed = await completed_analysis(client, pr_id, buyer)
    pr = prs.get(pr_id)
    quotation_rows = quotes.list_for_pr(pr_id)
    saved = service.by_analysis(completed["analysis_id"])
    legacy_revision = service._legacy_revision(pr, quotation_rows, saved["started_at"][:10])
    assert legacy_revision != service.revision(pr, quotation_rows)
    service.save({**saved, "snapshot_revision": legacy_revision})

    response = await client.get(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)

    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_buyer_review"
    assert service.by_analysis(completed["analysis_id"])["snapshot_revision"] == service.revision(pr, quotation_rows)


@pytest.mark.asyncio
async def test_legacy_snapshot_still_becomes_stale_when_a_confirmed_quotation_changes(client, integration):
    service, prs, quotes, _, _ = integration
    pr_id, buyer, _ = await prepare(client)
    completed = await completed_analysis(client, pr_id, buyer)
    pr = prs.get(pr_id)
    quotation_rows = quotes.list_for_pr(pr_id)
    saved = service.by_analysis(completed["analysis_id"])
    legacy_revision = service._legacy_revision(pr, quotation_rows, saved["started_at"][:10])
    service.save({**saved, "snapshot_revision": legacy_revision})
    records = quotes._load()
    records[0] = records[0].model_copy(update={"lead_time_days": 6})
    quotes._save(records)

    response = await client.get(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)

    assert response.status_code == 200
    assert response.json()["status"] == "stale"
    assert service.by_analysis(completed["analysis_id"])["snapshot_revision"] == legacy_revision


@pytest.mark.asyncio
async def test_duplicate_supplier_never_calls_model(client, integration):
    service, prs, quotes, pos, model = integration
    pr_id, buyer, manager = await prepare(client)
    records = quotes._load()
    records[0] = records[0].model_copy(
        update={"vat_rate": records[1].vat_rate, "supplier_name": records[1].supplier_name}
    )
    quotes._save(records)
    run_response = await client.post(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)
    assert run_response.status_code == 422
    run = (await client.get(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)).json()
    assert run["status"] == "needs_input" and model.calls == 0
    assert not pos.list()


@pytest.mark.asyncio
async def test_manager_cannot_revise_after_buyer_submission(client, integration):
    service, prs, quotes, pos, model = integration
    pr_id, buyer, manager = await prepare(client)
    run = await completed_analysis(client, pr_id, buyer)
    assert run["status"] == "awaiting_buyer_review"
    assert (
        await client.post(f"/api/v1/analyses/{run['analysis_id']}/submit-approval", headers=buyer, json={})
    ).status_code == 200
    path = f"/api/v1/recommendations/{run['recommendation_id']}/feedback"
    revised = await client.post(
        path,
        headers=manager,
        json={
            "feedback_id": "revision",
            "idempotency_key": "revision",
            "recommendation_id": run["recommendation_id"],
            "recommendation_version": 1,
            "decision": "revise",
            "revision_type": "explanation_change",
            "requested_changes": {"explanation_change": "Làm rõ đơn vị ngày lịch sau xác nhận đơn hàng."},
        },
    )
    assert revised.status_code == 409, revised.text
    assert prs.get(pr_id).status == "pending_approval" and not pos.list()
    unchanged = await client.get(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)
    assert unchanged.status_code == 200
    assert unchanged.json()["status"] == "pending_manager_approval"


@pytest.mark.asyncio
async def test_reject_then_reanalyze_gets_new_identity_and_reopen_invalidates_review(client, integration):
    service, prs, quotes, pos, model = integration
    pr_id, buyer, manager = await prepare(client)
    first = await completed_analysis(client, pr_id, buyer)
    assert (
        await client.post(f"/api/v1/analyses/{first['analysis_id']}/submit-approval", headers=buyer, json={})
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/recommendations/{first['recommendation_id']}/feedback",
            headers=manager,
            json={
                "feedback_id": "reject-and-rerun",
                "idempotency_key": "reject-and-rerun",
                "recommendation_id": first["recommendation_id"],
                "recommendation_version": first["recommendation_version"],
                "decision": "reject",
                "note": "Cần xem xét lại báo giá",
            },
        )
    ).status_code == 200
    rejected = await client.get(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert service.latest(pr_id)["manager_note"] == "Cần xem xét lại báo giá"
    assert prs.get(pr_id).status == "comparing"
    second = await completed_analysis(client, pr_id, buyer)
    assert second["status"] == "awaiting_buyer_review"
    assert first["recommendation_id"] != second["recommendation_id"]
    old_review = await client.get(f"/api/v1/recommendations/{first['recommendation_id']}/review", headers=manager)
    assert old_review.status_code == 409
    q = quotes.list_for_pr(pr_id)[0]
    assert (await client.post(f"/api/v1/quotations/{q.id}/reopen", headers=buyer)).status_code == 200
    stale = await client.get(f"/api/v1/recommendations/{second['recommendation_id']}/review", headers=manager)
    assert stale.status_code == 409
    assert (await client.post("/api/v1/analyses/missing/submit-approval", headers=buyer, json={})).status_code == 409


@pytest.mark.asyncio
async def test_evidence_unavailability_is_a_recoverable_run_not_an_approval(client, integration, monkeypatch):
    service, prs, quotes, pos, model = integration
    pr_id, buyer, manager = await prepare(client)
    adapter = service.evaluation.evaluator.retriever

    def unavailable(chunks):
        raise TimeoutError("Simulated evidence outage")

    monkeypatch.setattr(adapter, "ingest", unavailable)
    response = await completed_analysis(client, pr_id, buyer)
    assert response["status"] == "awaiting_buyer_review"
    assert model.calls == 1
    assert (await client.post("/api/v1/analyses/missing/submit-approval", headers=buyer, json={})).status_code == 409
    assert not pos.list()


@pytest.mark.asyncio
async def test_supplier_identity_is_server_owned_and_stable_after_reconfirmation(client, integration):
    service, prs, quotes, pos, model = integration
    pr_id, buyer, manager = await prepare(client)
    quote = quotes.list_for_pr(pr_id)[0]
    supplier_id = quote.supplier_id
    assert supplier_id and supplier_id != quote.supplier_name
    assert (await client.post(f"/api/v1/quotations/{quote.id}/reopen", headers=buyer)).status_code == 200
    payload = quote.confirmation_audit["submitted"]
    payload["supplier_id"] = "client-forged-identity"
    confirmed = await client.post(f"/api/v1/quotations/{quote.id}/confirm", headers=buyer, json=payload)
    assert confirmed.status_code == 200
    assert confirmed.json()["supplier_id"] == supplier_id
    assert prs.get(pr_id).quotation_count == 2
    run = await completed_analysis(client, pr_id, buyer)
    assert run["status"] == "awaiting_buyer_review", run
    assert supplier_id in run["supplier_names"]


@pytest.mark.asyncio
async def test_tco_rounding_mismatch_blocks_model_and_po(client, integration):
    from decimal import Decimal

    service, prs, quotes, pos, model = integration
    pr_id, buyer, manager = await prepare(client)
    records = quotes._load()
    q = records[0]
    q = q.model_copy(
        update={
            "items": [q.items[0].model_copy(update={"unit_price": Decimal("0.01"), "line_total": Decimal("0.10")})],
            "shipping_fee": Decimal("0.10"),
            "vat_rate": Decimal("0.05"),
        }
    )
    # Each declared component rounds 0.105 to 0.11; the existing tool rounds
    # the aggregate 0.21. The integration must expose the conflict, not approve it.
    q = q.model_copy(
        update={"goods_total_including_tax": Decimal("0.11"), "shipping_total_including_tax": Decimal("0.11")}
    )
    records[0] = q
    quotes._save(records)
    response = await client.post(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)
    assert response.status_code == 422
    run = (await client.get(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)).json()
    assert run["status"] == "needs_input"
    assert "làm tròn" in run["message"]
    assert model.calls == 0 and not pos.list()
