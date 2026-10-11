from __future__ import annotations

import importlib
import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.types import Command

import src.agents.graph as graph_module
from src.api.routes import pr as pr_routes
from src.api.routes.pr import case_store
from src.core.config import get_settings
from src.main import app
from src.services.evaluation.engine import Evaluator
from src.services.evaluation.evidence import ChromaEvidenceAdapter
from src.services.evaluation.store import EvaluationStore
from src.services.evaluation.workflow import EvaluationWorkflow
from tests.fixtures.evaluation_cases import FakeChroma, actor, chunks, context, proposal


@pytest.fixture(autouse=True)
def isolate_pr_storage(tmp_path, monkeypatch):
    """Keep in-memory cases and uploaded PDFs isolated between tests."""
    case_store.clear()
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    yield
    case_store.clear()


async def _create_pr(client, *, deadline: date | None = None) -> str:
    response = await client.post(
        "/api/prs",
        json={
            "pr_number": "PR-2026-001",
            "quantity": 10,
            "deadline": (deadline or date.today()).isoformat(),
        },
    )
    assert response.status_code == 201
    return response.json()["case_id"]


async def _upload_pdf(client, case_id: str, filename: str = "quote.pdf"):
    return await client.post(
        f"/api/prs/{case_id}/documents",
        files={"file": (filename, b"%PDF-1.7 stub", "application/pdf")},
    )


@pytest.mark.asyncio
async def test_create_pr_accepts_valid_data_and_today_deadline(client):
    response = await client.post(
        "/api/prs",
        json={
            "pr_number": "PR-2026-001",
            "quantity": 10,
            "deadline": date.today().isoformat(),
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "awaiting_documents"
    assert response.json()["same_day_deadline"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", 0),
        ("quantity", -1),
        ("deadline", (date.today() - timedelta(days=1)).isoformat()),
    ],
)
async def test_create_pr_rejects_invalid_data(client, field, value):
    payload = {
        "pr_number": "PR-2026-002",
        "quantity": 10,
        "deadline": date.today().isoformat(),
    }
    payload[field] = value

    response = await client.post("/api/prs", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_documents_accepts_pdf(client):
    case_id = await _create_pr(client)

    response = await _upload_pdf(client, case_id)

    assert response.status_code == 201
    assert response.json()["document_count"] == 1
    stored_document = case_store[case_id].documents[0]
    assert Path(stored_document.path).is_file()


@pytest.mark.asyncio
async def test_upload_documents_rejects_non_pdf(client):
    case_id = await _create_pr(client)

    response = await client.post(
        f"/api/prs/{case_id}/documents",
        files={"file": ("quote.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_documents_rejects_file_over_two_mb(client):
    case_id = await _create_pr(client)

    response = await client.post(
        f"/api/prs/{case_id}/documents",
        files={"file": ("large.pdf", b"x" * (2 * 1024 * 1024 + 1), "application/pdf")},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_documents_rejects_eleventh_file(client):
    case_id = await _create_pr(client)
    for index in range(10):
        response = await _upload_pdf(client, case_id, f"quote-{index}.pdf")
        assert response.status_code == 201

    response = await _upload_pdf(client, case_id, "quote-11.pdf")

    assert response.status_code == 400
    assert response.json()["detail"] == "Tối đa 10 báo giá mỗi PR"


@pytest.mark.asyncio
async def test_analyze_trigger_rejects_fewer_than_two_documents(client):
    case_id = await _create_pr(client)
    await _upload_pdf(client, case_id)

    response = await client.post(f"/api/prs/{case_id}/analyze")

    assert response.status_code == 400
    assert response.json()["detail"] == "Cần thêm 1 báo giá"


def _configure_evaluation(monkeypatch, tmp_path, case_id):
    c = context()
    c = c.model_copy(
        update={"case_id": case_id, "source_scope": c.source_scope.model_copy(update={"case_id": case_id})}
    )
    a = ChromaEvidenceAdapter(FakeChroma())
    a.ingest([chunk.model_copy(update={"case_id": case_id}) for chunk in chunks()])
    w = EvaluationWorkflow(Evaluator(a), EvaluationStore(tmp_path / "api-review.sqlite"))
    buyer = actor().model_copy(update={"case_ids": [case_id]})
    monkeypatch.setattr(pr_routes, "_actor", lambda request: buyer, raising=False)
    monkeypatch.setattr(app.state, "evaluation_workflow", w, raising=False)
    monkeypatch.setattr(app.state, "evaluation_context_provider", lambda case, actor: c, raising=False)
    return w, c


@pytest.mark.asyncio
async def test_analyze_trigger_runs_graph_and_returns_awaiting_review(client, monkeypatch, tmp_path):
    case_id = await _create_pr(client)
    await _upload_pdf(client, case_id, "quote-a.pdf")
    await _upload_pdf(client, case_id, "quote-b.pdf")
    workflow, c = _configure_evaluation(monkeypatch, tmp_path, case_id)
    calls = []

    class FakeAgent:
        async def ainvoke(self, value, config):
            calls.append((value, config))
            result = workflow.submit(proposal(), c)
            return {
                "workflow_status": "awaiting_review",
                "recommendation_id": "rec-demo",
                "recommendation_version": 1,
                "evaluation_result": result.model_dump(mode="json"),
            }

    monkeypatch.setattr(pr_routes, "build_graph", lambda **kwargs: FakeAgent())
    response = await client.post(f"/api/prs/{case_id}/analyze")
    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_review"
    assert response.json()["evaluation"]["overall_status"] == "ready_for_review"
    assert workflow.store.current("rec-demo")["status"] == "awaiting_review"
    initial_state, config = calls[0]
    assert initial_state["case_id"] == case_id
    assert initial_state["pr_data"]["target_currency"] == "VND"
    assert len(initial_state["documents"]) == 2
    assert config == {"configurable": {"thread_id": case_id}}
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_analyze_never_auto_approves_recommendation(client, monkeypatch, tmp_path):
    case_id = await _create_pr(client)
    await _upload_pdf(client, case_id, "quote-a.pdf")
    await _upload_pdf(client, case_id, "quote-b.pdf")
    workflow, c = _configure_evaluation(monkeypatch, tmp_path, case_id)
    calls = []

    class FakeAgent:
        async def ainvoke(self, value, config):
            calls.append((value, config))
            if len(calls) == 1:
                return {"__interrupt__": (SimpleNamespace(value={"checkpoint": "extraction_review"}),)}
            result = workflow.submit(proposal(), c)
            return {
                "workflow_status": "awaiting_review",
                "recommendation_id": "rec-demo",
                "recommendation_version": 1,
                "evaluation_result": result.model_dump(mode="json"),
            }

    monkeypatch.setattr(pr_routes, "build_graph", lambda **kwargs: FakeAgent())
    response = await client.post(f"/api/prs/{case_id}/analyze")
    assert response.status_code == 200
    assert response.json()["status"] == "needs_input"
    assert len(calls) == 1
    assert response.json()["recommendation_id"] is None
    assert not any(isinstance(value, Command) for value, _ in calls)
    with workflow.store.transaction() as db:
        assert db.execute("SELECT count(*) FROM feedback").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_analyze_deprecated_endpoint_projects_current_graph_result(client, monkeypatch, tmp_path):
    """The deprecated endpoint preserves the current graph's needs-input contract."""
    case_id = await _create_pr(client, deadline=date.today() + timedelta(days=30))
    await _upload_pdf(client, case_id, "quote-a.pdf")
    await _upload_pdf(client, case_id, "quote-b.pdf")

    workflow, c = _configure_evaluation(monkeypatch, tmp_path, case_id)

    def stub_extract_documents(state):
        return {
            "raw_extractions": [
                {
                    "extraction_id": f"line-{index}",
                    "source": {
                        "document_path": document,
                        "filename": Path(document).name,
                        "page_number": 1,
                    },
                    "supplier_id": "A" if index == 1 else "B",
                    "item_name": "procurement-item",
                    "unit_price": float(index * 100),
                    "quantity": 10.0,
                    "currency": "VND",
                    "vat_rate": 0.1,
                    "vat_included": False,
                    "surcharges": [],
                    "warranty_months": 12,
                    "lead_time_days": index * 2,
                    "confidence_score": 0.95,
                    "field_confidence": {
                        "unit_price": 0.95,
                    },
                }
                for index, document in enumerate(state["documents"], start=1)
            ]
        }

    class FakeResponse:
        content = json.dumps(
            {
                "status": "needs_input",
                "rationale": "Cần xác nhận báo giá trước khi đề xuất.",
                "input_artifact_ids": [],
            }
        )

    class FakeDecisionModel:
        def invoke(self, input: object) -> FakeResponse:
            return FakeResponse()

    decision_module = importlib.import_module("src.agents.nodes.decision_llm")
    monkeypatch.setattr(graph_module, "extract_documents", stub_extract_documents)
    monkeypatch.setattr(decision_module, "get_llm", lambda: FakeDecisionModel())
    monkeypatch.setattr(decision_module, "_has_decision_provider", lambda settings: True)

    class CurrentGraph:
        async def ainvoke(self, value, config):
            assert value["case_id"] == case_id
            assert config == {"configurable": {"thread_id": case_id}}
            return {"workflow_status": "needs_input"}

    monkeypatch.setattr(pr_routes, "build_graph", lambda: CurrentGraph())

    response = await client.post(f"/api/prs/{case_id}/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_input"
    assert body["recommendation_id"] is None
    assert body["evaluation"] is None
