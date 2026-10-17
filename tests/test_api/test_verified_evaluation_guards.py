"""Regression guards for the verified-review-only purchase-order boundary."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.domain.procurement.contracts import PurchaseOrder, PurchaseOrderItem
from tests.test_api.test_procurement_integration import prepare


async def _legacy_raw_run(client, integration):
    service, prs, quotes, _, _ = integration
    pr_id, buyer, manager = await prepare(client)
    pr = prs.get(pr_id)
    assert pr is not None
    quotation_rows = quotes.list_for_pr(pr_id)
    recommendation_id = "legacy-raw-proposal"
    state, context, _ = service.prepare(pr, quotation_rows, recommendation_id)
    run = {
        "analysis_id": "legacy-raw-analysis",
        "pr_id": pr_id,
        "recommendation_id": recommendation_id,
        "recommendation_version": 1,
        "snapshot_revision": service.revision(pr, quotation_rows),
        "status": "untrusted_proposal",
        "context": context.model_dump(mode="json"),
        "quotations": [
            {**quote.model_dump(mode="json"), "supplier_id": state["raw_extractions"][index]["supplier_id"]}
            for index, quote in enumerate(quotation_rows)
        ],
        "decision_proposal": {"decision": {"preferred_supplier_id": state["raw_extractions"][0]["supplier_id"]}},
    }
    service.save(run)
    assert prs.submit_for_approval(pr_id) is not None
    return service, prs, quotes, pr, manager, run


@pytest.mark.asyncio
async def test_raw_proposal_feedback_cannot_create_purchase_order(client, integration):
    # expected to fail until P1-T3: the former bypass created a PO from this raw payload.
    service, prs, _, pr, manager, run = await _legacy_raw_run(client, integration)
    with service.evaluation.store.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0] == 0

    response = await client.post(
        f"/api/v1/recommendations/{run['recommendation_id']}/feedback",
        headers=manager,
        json={
            "feedback_id": "raw-proposal-feedback",
            "idempotency_key": "raw-proposal-feedback",
            "recommendation_id": run["recommendation_id"],
            "recommendation_version": 1,
            "decision": "approve",
        },
    )

    assert response.status_code == 409
    assert not integration[3].list()
    assert prs.get(pr.id).status == "pending_approval"
    unchanged = service.latest(pr.id)
    assert unchanged["analysis_id"] == run["analysis_id"]
    assert unchanged["status"] == "untrusted_proposal"


@pytest.mark.asyncio
async def test_unverified_finalization_command_is_never_replayed(client, integration):
    # expected to fail until P1-T3: reconciliation formerly replayed raw approval commands.
    service, prs, quotes, pr, _, run = await _legacy_raw_run(client, integration)
    quote = run["quotations"][0]
    po = PurchaseOrder(
        id="legacy-raw-po",
        code="PO-LEGACY-RAW",
        pr_id=pr.id,
        pr_code=pr.code,
        quotation_id=quote["id"],
        supplier_name=quote["supplier_name"],
        items=[PurchaseOrderItem.model_validate(item) for item in quote["items"]],
        total_amount=Decimal(str(quote["goods_total_including_tax"])),
        currency=quote["currency"],
        approver_id="legacy-manager",
        approver_name="Legacy manager",
        recommendation_id=run["recommendation_id"],
        recommendation_version=1,
        snapshot_revision=run["snapshot_revision"],
    )
    with service.db() as db:
        db.execute(
            "INSERT INTO finalization VALUES (?,?)",
            (po.id, json.dumps({"po": po.model_dump(mode="json"), "pr_id": pr.id})),
        )

    assert service.reconcile(prs, quotes, integration[3]) == 0
    assert not integration[3].list()
    assert prs.get(pr.id).status == "pending_approval"


@pytest.mark.asyncio
async def test_legacy_raw_run_migrates_to_stale_and_reopens_pr(client, integration):
    service, prs, _, pr, buyer, run = await _legacy_raw_run(client, integration)

    assert service.migrate_legacy_runs(prs) == 1
    migrated = service.latest(pr.id)
    assert migrated["status"] == "stale"
    assert migrated["decision_proposal"] == run["decision_proposal"]
    assert prs.get(pr.id).status == "comparing"

    response = await client.get(f"/api/v1/prs/{pr.id}/analysis", headers=buyer)
    assert response.status_code == 200
    assert response.json()["status"] == "stale"
    assert response.json()["decision_proposal"] == run["decision_proposal"]


@pytest.mark.asyncio
async def test_verified_feedback_requires_manager_and_unchanged_snapshot(client, integration):
    service, prs, quotes, pos, _ = integration
    pr_id, buyer, manager = await prepare(client)

    assert (await client.post(f"/api/v1/prs/{pr_id}/analysis", headers=manager)).status_code == 403
    from tests.test_api.test_procurement_integration import completed_analysis

    run = await completed_analysis(client, pr_id, buyer)
    assert run["status"] == "awaiting_buyer_review"
    assert (
        await client.post(f"/api/v1/analyses/{run['analysis_id']}/submit-approval", headers=buyer, json={})
    ).status_code == 200

    feedback = {
        "feedback_id": "snapshot-feedback",
        "idempotency_key": "snapshot-feedback",
        "recommendation_id": run["recommendation_id"],
        "recommendation_version": run["recommendation_version"],
        "decision": "approve",
    }
    path = f"/api/v1/recommendations/{run['recommendation_id']}/feedback"
    assert (await client.post(path, headers=buyer, json=feedback)).status_code == 403

    Path(quotes.list_for_pr(pr_id)[0].source_path).write_text("changed after evaluation")
    assert (await client.post(path, headers=manager, json=feedback)).status_code == 409
    assert not pos.list()
    assert prs.get(pr_id).status == "pending_approval"
    assert service.latest(pr_id)["status"] == "pending_manager_approval"
