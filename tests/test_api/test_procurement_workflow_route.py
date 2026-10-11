from datetime import date, timedelta

import pytest

from src.api.routes.procurement_workflow import public_run
from src.models.procurement_workflow import ProcurementAnalysis
from src.models.schemas import PRStatus


def test_public_run_omits_internal_fields_from_legacy_analysis_snapshots():
    run = {
        "pr_id": "pr-1",
        "status": "awaiting_buyer_review",
        "analysis_id": "analysis-1",
        "started_at": "2026-10-05T05:37:06.087188+00:00",
        "manager_note": None,
        "decision_retry_count": 0,
        "finished_at": "2026-10-05T05:38:02.195250+00:00",
        "context": {"must_not": "leave the server"},
        "quotations": [{"must_not": "leave the server"}],
    }

    assert public_run(run) == {
        "pr_id": "pr-1",
        "status": "awaiting_buyer_review",
        "analysis_id": "analysis-1",
    }


def test_public_run_projects_v1_analysis_artifacts_to_the_browser_contract():
    result = public_run(
        {
            "pr_id": "pr-1",
            "status": "awaiting_buyer_review",
            "tco_results": [
                {
                    "supplier_id": "supplier-1",
                    "quotation_revision_id": "revision-private",
                    "currency": "VND",
                    "subtotal": "100.00",
                    "total_surcharges": "0.00",
                    "total_vat": "10.00",
                    "total_tco": "110.00",
                    "status": "calculated",
                    "missing_fields": [],
                    "breakdown": [
                        {
                            "item_name": "Thép D16",
                            "quantity": "20",
                            "unit_price": "5.00",
                            "subtotal": "100.00",
                            "surcharges": "0.00",
                            "vat_rate": "0.10",
                            "vat_amount": "10.00",
                            "item_tco": "110.00",
                        }
                    ],
                }
            ],
            "risk_flags": [
                {
                    "supplier_id": "supplier-1",
                    "risk_type": "lead_time_exceeded",
                    "severity": "high",
                    "description": "Vượt hạn giao 2 ngày.",
                    "details": {"delta": 2},
                }
            ],
        }
    )

    assert result["tco_results"] == [
        {
            "supplier_id": "supplier-1",
            "items_tco": [
                {
                    "item_name": "Thép D16",
                    "quantity": "20",
                    "unit_price": "5.00",
                    "subtotal": "100.00",
                    "surcharges": "0.00",
                    "vat_rate": "0.10",
                    "vat_included": False,
                    "item_tco": "110.00",
                }
            ],
            "subtotal": "100.00",
            "total_surcharges": "0.00",
            "total_vat": "10.00",
            "total_tco": "110.00",
            "status": "calculated",
            "missing_fields": [],
        }
    ]
    assert result["risk_flags"] == [
        {
            "supplier_id": "supplier-1",
            "risk_type": "lead_time_exceeded",
            "severity": "error",
            "message": "Vượt hạn giao 2 ngày.",
            "detail": {"delta": 2},
            "source": None,
        }
    ]
    ProcurementAnalysis.model_validate(result)


def test_public_run_maps_unknown_legacy_status_to_stale():
    result = public_run({"pr_id": "pr-legacy", "status": "awaiting_review"})

    assert result["status"] == "stale"
    assert result["message"] == "Đề xuất cũ chưa được kiểm chứng. Hãy phân tích lại trước khi gửi duyệt."
    ProcurementAnalysis.model_validate(result)


@pytest.mark.asyncio
async def test_migrate_awaiting_review_run_is_idempotent_and_route_stays_readable(client, integration):
    service, prs, _, _, _ = integration
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "purchasing@vinuni.edu.vn", "password": "Purchase123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    created = await client.post(
        "/api/v1/prs",
        headers=headers,
        json={
            "code": "PR-LEGACY-STATUS",
            "category": "Thiết bị legacy",
            "quantity": 1,
            "estimated_budget": "1000000",
            "delivery_due_date": (date.today() + timedelta(days=10)).isoformat(),
        },
    )
    pr_id = created.json()["id"]
    records = prs._load()
    records[0] = records[0].model_copy(update={"status": PRStatus.PENDING_APPROVAL})
    prs._save(records)
    service.save(
        {
            "analysis_id": "legacy-awaiting-review",
            "pr_id": pr_id,
            "snapshot_revision": "legacy",
            "status": "awaiting_review",
            "audit_payload": {"must_remain": True},
        }
    )

    assert service.migrate_legacy_runs(prs) == 1
    assert service.latest(pr_id)["status"] == "stale"
    assert service.latest(pr_id)["audit_payload"] == {"must_remain": True}
    assert prs.get(pr_id).status == PRStatus.COMPARING
    assert service.migrate_legacy_runs(prs) == 0

    response = await client.get(f"/api/v1/prs/{pr_id}/analysis", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "stale"
