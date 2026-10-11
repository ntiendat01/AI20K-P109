"""API-level recovery states exposed to the comparison screen."""

from __future__ import annotations

import json

import pytest

from tests.fixtures.procurement_integration import ConfirmedDecisionModel
from tests.test_api.test_procurement_integration import completed_analysis, prepare


class InvalidJsonModel:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, messages: object) -> str:
        del messages
        self.calls += 1
        return "{}"


class InvalidRankingModel(ConfirmedDecisionModel):
    def invoke(self, messages):
        payload = json.loads(super().invoke(messages))
        payload["ranked_supplier_ids"] = [payload["preferred_supplier_id"], payload["preferred_supplier_id"]]
        return json.dumps(payload)


@pytest.mark.asyncio
async def test_technical_failure_is_retryable_and_cannot_be_submitted(client, integration):
    service, _, _, pos, _ = integration
    pr_id, buyer, _ = await prepare(client)
    model = InvalidJsonModel()
    service.decision_model = model

    run = await completed_analysis(client, pr_id, buyer)
    assert run["status"] == "needs_input"
    assert "không đúng DecisionProposal" in run["message"]
    assert model.calls == 1
    assert (await client.post("/api/v1/analyses/missing/submit-approval", headers=buyer, json={})).status_code == 409
    assert not pos.list()


@pytest.mark.asyncio
async def test_repairable_proposal_exposes_issues_and_cannot_be_submitted(client, integration):
    service, _, _, pos, _ = integration
    pr_id, buyer, _ = await prepare(client)
    service.decision_model = InvalidRankingModel()

    run = await completed_analysis(client, pr_id, buyer)
    assert run["status"] == "needs_input"
    assert "tham chiếu dữ liệu ngoài analysis snapshot" in run["message"]
    assert (await client.post("/api/v1/analyses/missing/submit-approval", headers=buyer, json={})).status_code == 409
    assert not pos.list()
