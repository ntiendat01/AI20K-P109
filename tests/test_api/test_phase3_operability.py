"""P3 acceptance tests: async work, cache/trace and cross-store recovery."""

from __future__ import annotations

import time

import pytest

from src.domain.analysis.evaluation import Feedback
from tests.fixtures.procurement_integration import ConfirmedDecisionModel
from tests.test_api.test_procurement_integration import completed_analysis, prepare


class SlowDecisionModel(ConfirmedDecisionModel):
    def invoke(self, messages):
        time.sleep(0.35)
        return super().invoke(messages)


@pytest.mark.asyncio
async def test_analysis_returns_202_without_waiting_and_reuses_running_snapshot(client, integration):
    service, _, _, _, _ = integration
    pr_id, buyer, _ = await prepare(client)
    slow = SlowDecisionModel()
    service.decision_model = slow

    started_at = time.perf_counter()
    first = await client.post(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)
    elapsed = time.perf_counter() - started_at
    second = await client.post(f"/api/v1/prs/{pr_id}/analysis", headers=buyer)

    assert first.status_code == 202
    assert elapsed < 1
    assert first.json()["status"] == "running"
    assert second.status_code == 200
    assert second.json()["analysis_id"] == first.json()["analysis_id"]

    final = await completed_analysis(client, pr_id, buyer)
    assert final["status"] == "awaiting_buyer_review"
    assert slow.calls == 1
    assert {"normalize", "calculate_tco", "analyze_risks", "compare_suppliers", "decision_llm"} == {
        event["node"] for event in final["events"]
    }
    for event in final["events"]:
        assert set(event) == {"node", "at"}


@pytest.mark.asyncio
async def test_force_reruns_graph_but_reuses_evidence_chunks(client, integration, monkeypatch):
    service, _, _, _, model = integration
    pr_id, buyer, _ = await prepare(client)
    adapter = service.evaluation.evaluator.retriever
    original_ingest = adapter.ingest
    ingested_batches = []

    def counting_ingest(chunks):
        ingested_batches.append(list(chunks))
        return original_ingest(chunks)

    monkeypatch.setattr(adapter, "ingest", counting_ingest)
    first = await completed_analysis(client, pr_id, buyer)
    cached = await completed_analysis(client, pr_id, buyer)
    forced = await completed_analysis(client, pr_id, buyer, force=True)

    assert first["analysis_id"] == cached["analysis_id"]
    assert first["analysis_id"] != forced["analysis_id"]
    assert model.calls == 2
    # The forced graph reuses exact cached Chroma chunks; it does not upsert a
    # second copy of the same quotation/authenticated-edit source snapshot.
    assert ingested_batches == []


def test_expired_running_run_is_recovered_when_read(integration):
    service, prs, quotes, _, _ = integration
    pr = prs.list()[0] if prs.list() else None
    if pr is None:
        from src.domain.procurement.contracts import PurchaseRequestCreate
        from src.infrastructure.auth import DemoUser

        pr = prs.create(
            PurchaseRequestCreate(
                code="PR-TIMEOUT",
                category="Timeout fixture",
                quantity=1,
                estimated_budget="10",
                delivery_due_date="2026-12-31",
            ),
            DemoUser(id="buyer", name="Buyer", email="buyer@example.com", password="test", role="procurement"),
        )
    # No worker is dispatched: this is the same durable state left by a process
    # crash between 202 and background execution.
    service.save(
        {
            "analysis_id": "stuck-analysis",
            "pr_id": pr.id,
            "recommendation_id": "stuck-recommendation",
            "recommendation_version": 1,
            "snapshot_revision": "stuck-revision",
            "status": "running",
            "started_at": "2000-01-01T00:00:00+00:00",
            "events": [],
        }
    )

    recovered = service.latest(pr.id)

    assert recovered["status"] == "technical_failure"
    assert "gián đoạn" in recovered["message"]
    assert recovered["finished_at"]


def test_timestamped_run_wins_over_legacy_uuid_when_read(integration):
    service, _, _, _, _ = integration
    pr_id = "mixed-generation-pr"
    # This UUID intentionally sorts after a date string. It represents an old
    # persisted run created before P3 added an immutable start timestamp.
    service.save(
        {
            "analysis_id": "fffffff-legacy",
            "pr_id": pr_id,
            "recommendation_id": "legacy-rec",
            "recommendation_version": 1,
            "snapshot_revision": "old",
            "status": "stale",
            "events": [],
        }
    )
    service.save(
        {
            "analysis_id": "new-running-analysis",
            "pr_id": pr_id,
            "recommendation_id": "new-rec",
            "recommendation_version": 1,
            "snapshot_revision": "new",
            "status": "running",
            "started_at": "2026-10-04T12:00:00+00:00",
            "events": [],
        }
    )

    assert service.latest(pr_id)["analysis_id"] == "new-running-analysis"


@pytest.mark.asyncio
async def test_retry_after_po_created_before_pr_update_is_idempotent_and_auditable(client, integration, monkeypatch):
    service, prs, quotes, pos, _ = integration
    pr_id, buyer, manager = await prepare(client)
    run = await completed_analysis(client, pr_id, buyer)
    assert (
        await client.post(f"/api/v1/analyses/{run['analysis_id']}/submit-approval", headers=buyer, json={})
    ).status_code == 200
    feedback = Feedback.model_validate(
        {
            "feedback_id": "post-po-failure",
            "idempotency_key": "post-po-failure",
            "recommendation_id": run["recommendation_id"],
            "recommendation_version": run["recommendation_version"],
            "decision": "approve",
        }
    )
    from src.infrastructure.auth import get_session

    manager_user = get_session(manager["Authorization"].removeprefix("Bearer ")).user
    original_approve = prs.approve

    def fail_after_po(*_args, **_kwargs):
        raise OSError("simulated failure after idempotent PO create")

    monkeypatch.setattr(prs, "approve", fail_after_po)
    with pytest.raises(OSError):
        service.feedback(feedback, manager_user, prs, quotes, pos)
    assert len(pos.list()) == 1
    assert prs.get(pr_id).status == "pending_approval"

    monkeypatch.setattr(prs, "approve", original_approve)
    result = service.feedback(feedback, manager_user, prs, quotes, pos)

    assert result["status"] == "approved"
    assert prs.get(pr_id).status == "approved"
    assert len(pos.list()) == 1
    findings = service.audit_consistency(prs, pos)
    assert findings == []


def test_consistency_audit_reports_but_does_not_repair(integration):
    service, prs, _, pos, _ = integration
    service.save(
        {
            "analysis_id": "orphaned-review-run",
            "pr_id": "missing-pr",
            "recommendation_id": "missing-recommendation",
            "recommendation_version": 1,
            "snapshot_revision": "orphaned",
            "status": "awaiting_review",
            "events": [],
        }
    )

    findings = service.audit_consistency(prs, pos)

    assert findings == [
        {
            "code": "AWAITING_REVIEW_WITHOUT_RECOMMENDATION",
            "pr_id": "missing-pr",
            "recommendation_id": "missing-recommendation",
        }
    ]
