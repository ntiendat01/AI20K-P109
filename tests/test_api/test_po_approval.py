import hashlib
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from src.domain.procurement.contracts import PRStatus, PurchaseRequest, Quotation, QuotationItem, QuotationStatus
from src.infrastructure.auth import DemoUser, create_session
from src.infrastructure.quotation.repository import QuotationRepository
from src.infrastructure.repositories.purchase_orders import PurchaseOrderRepository
from src.infrastructure.repositories.purchase_requests import PurchaseRequestRepository
from src.main import app


@pytest.fixture
def manager_token():
    user = DemoUser(
        id="user-manager-01",
        name="Trần Văn Quản Lý",
        email="quanghuy@dotcom.vn",
        role="manager",
        password="Manager123!",
    )
    token, _ = create_session(user)
    return token


@pytest.fixture
def procurement_token():
    user = DemoUser(
        id="user-procurement-01",
        name="Nguyễn Minh Anh",
        email="anhnm@dotcom.vn",
        role="procurement",
        password="Purchase123!",
    )
    token, _ = create_session(user)
    return token


@pytest.fixture
def sample_pr_and_quotes(tmp_path):
    pr_repo = PurchaseRequestRepository(tmp_path / "prs.json")
    q_repo = QuotationRepository(tmp_path / "quotes.json", tmp_path / "uploads")
    po_repo = PurchaseOrderRepository(tmp_path / "pos.json")

    pr = PurchaseRequest(
        id="pr-test-po-001",
        code="PR-TEST-PO",
        creator_id="user-procurement-01",
        creator_name="Nguyễn Minh Anh",
        category="Máy in 3D & Phụ kiện",
        quantity=2,
        estimated_budget=Decimal("50000000"),
        delivery_due_date=date.today() + timedelta(days=20),
        status=PRStatus.PENDING_APPROVAL,
        quotation_count=2,
    )
    pr_repo._save([pr])

    q1 = Quotation(
        id="q-po-001",
        pr_id="pr-test-po-001",
        supplier_name="Công ty In 3D Số 1",
        source_filename="quote1.pdf",
        source_hash="h1",
        source_path=str(tmp_path / "uploads/quote1.pdf"),
        source_content_type="application/pdf",
        delivery_time="7 ngày làm việc",
        payment_terms="Thanh toán 100% sau nghiệm thu",
        warranty="24 tháng",
        currency="VNĐ",
        status=QuotationStatus.CONFIRMED,
        items=[
            QuotationItem(
                product_name="Máy in 3D Pro",
                product_code="3D-PRO",
                unit="Máy",
                quantity=2,
                unit_price=Decimal("20000000"),
                line_total=Decimal("40000000"),
            )
        ],
    )
    q2 = Quotation(
        id="q-po-002",
        pr_id="pr-test-po-001",
        supplier_name="Công ty Thiết bị Đỉnh Cao",
        source_filename="quote2.pdf",
        source_hash="h2",
        source_path=str(tmp_path / "uploads/quote2.pdf"),
        source_content_type="application/pdf",
        delivery_time="10 ngày làm việc",
        payment_terms="Đặt cọc 30%",
        warranty="12 tháng",
        currency="VNĐ",
        status=QuotationStatus.CONFIRMED,
        items=[
            QuotationItem(
                product_name="Máy in 3D Pro",
                product_code="3D-PRO",
                unit="Máy",
                quantity=2,
                unit_price=Decimal("22000000"),
                line_total=Decimal("44000000"),
            )
        ],
    )
    for quote, days, warranty in [(q1, 7, 24), (q2, 10, 12)]:
        from pathlib import Path

        source = Path(quote.source_path)
        source.parent.mkdir(parents=True, exist_ok=True)
        content = f"Anonymous quote {quote.id}".encode()
        source.write_bytes(content)
        quote.source_hash = hashlib.sha256(content).hexdigest()
        quote.supplier_id = f"supplier:{quote.id}"
        quote.currency = "VND"
        quote.vat_rate = Decimal("0")
        quote.vat_included = True
        quote.shipping_fee = Decimal("0")
        quote.lead_time_days = days
        quote.warranty_months = warranty
        quote.goods_total_including_tax = sum(item.line_total for item in quote.items)
        quote.shipping_total_including_tax = Decimal("0")
        quote.confirmation_audit = {"audit_id": f"edit:{quote.id}", "actor_id": "user-procurement-01"}
    q_repo._save([q1, q2])
    yield pr_repo, q_repo, po_repo, pr, [q1, q2]
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_manager_can_list_pending_approvals(sample_pr_and_quotes, manager_token):
    pr_repo, q_repo, po_repo, pr, _ = sample_pr_and_quotes

    from src.api.routes import get_po_repository, get_pr_repository, get_quotation_repository

    app.dependency_overrides[get_pr_repository] = lambda: pr_repo
    app.dependency_overrides[get_quotation_repository] = lambda: q_repo
    app.dependency_overrides[get_po_repository] = lambda: po_repo

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/approvals", headers={"Authorization": f"Bearer {manager_token}"})

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    prs = resp.json()
    assert len(prs) == 1
    assert prs[0]["id"] == pr.id


@pytest.mark.asyncio
async def test_purchase_order_page_supports_search_sort_and_pagination(sample_pr_and_quotes, procurement_token):
    from datetime import datetime

    from src.api.routes import get_po_repository
    from src.domain.procurement.contracts import PurchaseOrder, PurchaseOrderItem

    _, _, po_repo, pr, quotes = sample_pr_and_quotes
    item = PurchaseOrderItem(
        product_name="Mặt hàng kiểm thử",
        quantity=1,
        unit_price=Decimal("1000000"),
        line_total=Decimal("1000000"),
    )
    for index, code in enumerate(("PO-003", "PO-001", "PO-002"), start=1):
        po_repo.create(PurchaseOrder(
            id=f"po-page-{index}",
            code=code,
            pr_id=pr.id,
            pr_code=pr.code,
            quotation_id=quotes[0].id,
            supplier_name=f"Nhà cung cấp {index}",
            items=[item],
            total_amount=Decimal(index * 1000000),
            approver_id="manager-1",
            approver_name="Quản lý kiểm thử",
            approved_at=datetime(2026, 1, index),
        ))
    app.dependency_overrides[get_po_repository] = lambda: po_repo

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_page = await client.get(
            "/api/v1/pos/page?page=1&page_size=2&sort_by=code&sort_direction=asc",
            headers={"Authorization": f"Bearer {procurement_token}"},
        )
        filtered = await client.get(
            "/api/v1/pos/page?query=Nh%C3%A0%20cung%20c%E1%BA%A5p%202&supplier=Nh%C3%A0%20cung%20c%E1%BA%A5p%202",
            headers={"Authorization": f"Bearer {procurement_token}"},
        )

    app.dependency_overrides.clear()
    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert [row["code"] for row in first_page.json()["items"]] == ["PO-001", "PO-002"]
    assert first_page.json()["page"] == 1
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["supplier_name"] == "Nhà cung cấp 2"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/prs/pr-legacy/submit-approval", {}),
        ("/api/v1/prs/pr-legacy/approve", {}),
        ("/api/v1/prs/pr-legacy/reject", {"rejection_reason": "Không dùng route cũ."}),
    ],
)
async def test_legacy_pr_approval_routes_are_removed(path, payload, procurement_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            path,
            json=payload,
            headers={"Authorization": f"Bearer {procurement_token}"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_po_code_collision_handling(sample_pr_and_quotes):
    _, _, po_repo, pr, quotes = sample_pr_and_quotes
    from datetime import datetime

    from src.domain.procurement.contracts import POStatus, PurchaseOrder, PurchaseOrderItem

    item = PurchaseOrderItem(
        product_name="Mặt hàng 1", quantity=1, unit_price=Decimal("1000000"), line_total=Decimal("1000000")
    )
    po1 = PurchaseOrder(
        id="po-collision-1",
        code="PO-COLLISION-TEST",
        pr_id=pr.id,
        pr_code=pr.code,
        quotation_id=quotes[0].id,
        supplier_name=quotes[0].supplier_name,
        items=[item],
        total_amount=Decimal("1000000"),
        status=POStatus.DRAFT,
        approver_id="mgr-1",
        approver_name="Manager 1",
        approved_at=datetime.now(),
    )
    created1 = po_repo.create(po1)
    assert created1.code == "PO-COLLISION-TEST"

    # Creating second PO with exact same code should automatically resolve to -1 without error
    po2 = po1.model_copy(update={"id": "po-collision-2"})
    created2 = po_repo.create(po2)
    assert created2.code == "PO-COLLISION-TEST-1"
