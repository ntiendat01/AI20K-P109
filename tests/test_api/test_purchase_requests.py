import logging
from datetime import date, timedelta

import pytest

from src.main import app
from src.services.procurement.purchase_requests import PurchaseRequestRepository, get_pr_repository
from tests.test_api.test_procurement_integration import completed_analysis

PROCUREMENT_CREDENTIALS = {
    "email": "purchasing@vinuni.edu.vn",
    "password": "Purchase123!",
}
MANAGER_CREDENTIALS = {
    "email": "manager@vinuni.edu.vn",
    "password": "Manager123!",
}


@pytest.fixture
def pr_store(tmp_path):
    repository = PurchaseRequestRepository(tmp_path / "purchase_requests.json")
    app.dependency_overrides[get_pr_repository] = lambda: repository
    yield repository
    app.dependency_overrides.pop(get_pr_repository, None)


async def procurement_headers(client):
    response = await client.post("/api/v1/auth/login", json=PROCUREMENT_CREDENTIALS)
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def purchase_request_payload(**overrides):
    payload = {
        "code": "PR-202609-001",
        "category": "Máy tính xách tay phục vụ nhóm nghiên cứu",
        "requested_quantity": 10,
        "requested_uom": "cái",
        "target_currency": "VND",
        "estimated_budget": "250000000.00",
        "delivery_due_date": (date.today() + timedelta(days=14)).isoformat(),
        "metadata": {"target_currency": "VND"},
        "items": [{"order_index": 0, "product_name": "Laptop", "quantity": 10, "unit": "cái", "notes": ""}]
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_procurement_user_can_create_pr_in_awaiting_quotation_status(client, pr_store, caplog):
    # Given
    caplog.set_level(logging.INFO)
    headers = await procurement_headers(client)
    caplog.clear()

    # When
    response = await client.post("/api/v1/prs", json=purchase_request_payload(), headers=headers)

    # Then
    assert response.status_code == 201
    data = response.json()
    audit_logs = [record for record in caplog.records if getattr(record, "event", None) == "pr_created"]
    assert data["code"] == "PR-202609-001"
    assert data["status"] == "awaiting_quotation"
    assert data["quotation_count"] == 0
    assert data["creator_name"] == "Nguyễn Minh Anh"
    assert len(audit_logs) == 1
    assert audit_logs[0].resource_id == data["id"]


@pytest.mark.asyncio
async def test_pr_list_can_filter_by_status(client, pr_store):
    headers = await procurement_headers(client)
    await client.post("/api/v1/prs", json=purchase_request_payload(), headers=headers)

    matching = await client.get("/api/v1/prs?status=awaiting_quotation", headers=headers)
    empty = await client.get("/api/v1/prs?status=approved", headers=headers)

    assert matching.status_code == 200
    assert len(matching.json()) == 1
    assert empty.status_code == 200
    assert empty.json() == []


@pytest.mark.asyncio
async def test_pr_detail_displays_request_and_attached_quotation_count(client, pr_store):
    headers = await procurement_headers(client)
    created = await client.post("/api/v1/prs", json=purchase_request_payload(), headers=headers)

    response = await client.get(f"/api/v1/prs/{created.json()['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["quotation_count"] == 0


@pytest.mark.asyncio
async def test_pr_can_be_edited_only_after_all_uploaded_quotations_are_removed(client, integration):
    headers = await procurement_headers(client)
    created = await client.post("/api/v1/prs", json=purchase_request_payload(), headers=headers)
    request_id = created.json()["id"]
    edit_payload = purchase_request_payload(
        category="Máy tính xách tay cho phòng thí nghiệm",
        estimated_budget="275000000.00",
    )

    updated = await client.patch(f"/api/v1/prs/{request_id}", json=edit_payload, headers=headers)

    assert updated.status_code == 200
    assert updated.json()["category"] == edit_payload["category"]
    assert updated.json()["estimated_budget"] == edit_payload["estimated_budget"]

    uploaded = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        files={
            "file": (
                "bao-gia.txt",
                b"Supplier: Vendor A\\nWidget | 10 | 1000 | 10000",
                "text/plain",
            )
        },
        headers=headers,
    )
    assert uploaded.status_code == 201

    blocked = await client.patch(f"/api/v1/prs/{request_id}", json=edit_payload, headers=headers)
    assert blocked.status_code == 409
    assert "xóa hết báo giá" in blocked.json()["detail"]

    deleted = await client.delete(f"/api/v1/quotations/{uploaded.json()['id']}", headers=headers)
    assert deleted.status_code == 204

    updated_again = await client.patch(f"/api/v1/prs/{request_id}", json=edit_payload, headers=headers)
    assert updated_again.status_code == 200


@pytest.mark.asyncio
async def test_first_quotation_and_buyer_submission_advance_pr_status(client, pr_store, integration):
    pr_store = integration[1]
    headers = await procurement_headers(client)
    created = await client.post("/api/v1/prs", json=purchase_request_payload(), headers=headers)
    request_id = created.json()["id"]

    with_quotation = pr_store.register_quotation(request_id)
    for supplier, price in [("Vendor A", 1000), ("Vendor B", 1200)]:
        uploaded = await client.post(
            f"/api/v1/prs/{request_id}/quotations",
            headers=headers,
            files={
                "file": (
                    f"{supplier}.txt",
                    f"Supplier: {supplier}\nWidget | 10 | {price} | {price * 10}".encode(),
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201
        confirmed = await client.post(
            f"/api/v1/quotations/{uploaded.json()['id']}/confirm",
            headers=headers,
            json={
                "supplier_name": supplier,
                "currency": "VND",
                "vat_rate": "0.1",
                "vat_included": False,
                "shipping_fee": "0",
                "lead_time_days": 5 if supplier == "Vendor A" else 7,
                "warranty_months": 12 if supplier == "Vendor A" else 24,
                "goods_total_including_tax": str(price * 11),
                "shipping_total_including_tax": "0",
                "items": [
                    {
                        "product_name": "Widget",
                        "quantity": 10,
                        "unit": "cái",
                        "unit_price": price,
                        "line_total": price * 10,
                    }
                ],
            },
        )
        assert confirmed.status_code == 200
    analyzed = await completed_analysis(client, request_id, headers)
    assert analyzed["status"] == "awaiting_buyer_review", analyzed
    submitted = await client.post(
        f"/api/v1/analyses/{analyzed['analysis_id']}/submit-approval",
        headers=headers,
        json={},
    )

    assert with_quotation.status == "comparing"
    assert with_quotation.quotation_count == 1
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending_manager_approval"


@pytest.mark.asyncio
async def test_pr_without_quotation_remains_awaiting_quotation(client, pr_store):
    headers = await procurement_headers(client)
    created = await client.post("/api/v1/prs", json=purchase_request_payload(), headers=headers)

    response = await client.get(f"/api/v1/prs/{created.json()['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_quotation"


@pytest.mark.asyncio
async def test_pr_rejects_invalid_quantity_budget_and_delivery_date(client, pr_store):
    headers = await procurement_headers(client)
    response = await client.post(
        "/api/v1/prs",
        json=purchase_request_payload(requested_quantity=0, estimated_budget="0", delivery_due_date=date.today().isoformat()),
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_manager_cannot_create_or_view_procurement_prs(client, pr_store):
    login_response = await client.post("/api/v1/auth/login", json=MANAGER_CREDENTIALS)
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    create_response = await client.post("/api/v1/prs", json=purchase_request_payload(), headers=headers)
    list_response = await client.get("/api/v1/prs", headers=headers)

    assert create_response.status_code == 403
    assert list_response.status_code == 403
