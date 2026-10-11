from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models.schemas import (
    PRStatus,
    PurchaseRequest,
    Quotation,
    QuotationItem,
    QuotationStatus,
)
from src.services.auth import DemoUser, create_session
from src.services.procurement.purchase_requests import PurchaseRequestRepository
from src.services.quotation.repository import QuotationRepository


@pytest.fixture
def procurement_token():
    user = DemoUser(
        id="user-procurement-01",
        name="Nguyễn Minh Anh",
        email="purchasing@vinuni.edu.vn",
        role="procurement",
        password="Purchase123!",
    )
    token, _ = create_session(user)
    return token


@pytest.fixture
def sample_pr(tmp_path):
    repo = PurchaseRequestRepository(tmp_path / "prs.json")
    pr = PurchaseRequest(
        id="test-pr-001",
        code="PR-TEST-001",
        creator_id="user-procurement-01",
        creator_name="Nguyễn Minh Anh",
        category="Thiết bị máy tính",
        quantity=5,
        estimated_budget=Decimal("100000000"),
        delivery_due_date=date.today() + timedelta(days=15),
        status=PRStatus.COMPARING,
        quotation_count=2,
    )
    repo._save([pr])
    return repo, pr


@pytest.fixture
def sample_quotations(tmp_path):
    q_repo = QuotationRepository(tmp_path / "quotes.json", tmp_path / "uploads")
    q1 = Quotation(
        id="q-001",
        pr_id="test-pr-001",
        supplier_name="Công ty Tin học ABC",
        source_filename="abc.pdf",
        source_hash="hash1",
        source_path=str(tmp_path / "uploads/abc.pdf"),
        source_content_type="application/pdf",
        delivery_time="5 ngày làm việc",
        payment_terms="Thanh toán trong 15 ngày",
        warranty="24 tháng",
        currency="VNĐ",
        status=QuotationStatus.CONFIRMED,
        items=[
            QuotationItem(
                product_name="Laptop Dell Latitude",
                product_code="DELL-LAT",
                unit="Chiếc",
                quantity=5,
                unit_price=Decimal("18000000"),
                line_total=Decimal("90000000"),
            )
        ],
    )
    q2 = Quotation(
        id="q-002",
        pr_id="test-pr-001",
        supplier_name="Công ty Công nghệ XYZ",
        source_filename="xyz.pdf",
        source_hash="hash2",
        source_path=str(tmp_path / "uploads/xyz.pdf"),
        source_content_type="application/pdf",
        delivery_time="10 ngày làm việc",
        payment_terms="Đặt cọc 50% trước khi giao",
        warranty="12 tháng",
        currency="VNĐ",
        status=QuotationStatus.CONFIRMED,
        items=[
            QuotationItem(
                product_name="Laptop Dell Latitude",
                product_code="DELL-LAT",
                unit="Chiếc",
                quantity=5,
                unit_price=Decimal("19000000"),
                line_total=Decimal("95000000"),
            )
        ],
    )
    q_repo._save([q1, q2])
    return q_repo, [q1, q2]


@pytest.mark.asyncio
async def test_get_comparison_success(sample_pr, sample_quotations, procurement_token):
    pr_repo, pr = sample_pr
    q_repo, _ = sample_quotations

    from src.api.routes import get_pr_repository, get_quotation_repository

    app.dependency_overrides[get_pr_repository] = lambda: pr_repo
    app.dependency_overrides[get_quotation_repository] = lambda: q_repo

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/prs/{pr.id}/comparison",
            headers={"Authorization": f"Bearer {procurement_token}"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["pr"]["id"] == pr.id
    assert len(data["suppliers"]) == 2
    assert len(data["items"]) == 1
    assert data["recommendation"]["recommended_supplier"] == "Công ty Tin học ABC"
    assert len(data["recommendation"]["execution_steps"]) == 4
    assert "detailed_rationale" in data["recommendation"]


@pytest.mark.asyncio
async def test_get_comparison_pr_not_found(procurement_token, tmp_path):
    from src.api.routes import get_pr_repository, get_quotation_repository

    pr_repo = PurchaseRequestRepository(tmp_path / "empty_prs.json")
    q_repo = QuotationRepository(tmp_path / "empty_q.json", tmp_path / "uploads")

    app.dependency_overrides[get_pr_repository] = lambda: pr_repo
    app.dependency_overrides[get_quotation_repository] = lambda: q_repo

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/prs/non-existing-id/comparison",
            headers={"Authorization": f"Bearer {procurement_token}"},
        )

    app.dependency_overrides.clear()
    assert response.status_code == 404


def test_extract_warranty_and_payment_terms_robustness():
    from src.services.procurement.comparison import analyze_payment_terms, extract_warranty_months

    # Test warranty
    assert extract_warranty_months("1 năm") == 12
    assert extract_warranty_months("2 năm chính hãng") == 24
    assert extract_warranty_months("18 tháng") == 18
    assert extract_warranty_months("Warranty for 2 items is 12 months") == 12
    assert extract_warranty_months("24") == 24
    assert extract_warranty_months("bảo hành: 36") == 36
    assert extract_warranty_months("Model XYZ-24, không bảo hành") == 0
    assert extract_warranty_months("không bảo hành") == 0
    assert extract_warranty_months("") == 0
    assert extract_warranty_months("chưa có bảo hành") == 0
    # Test câu bảo hành có chứa từ 'không' trong điều kiện (bug fix)
    assert (
        extract_warranty_months(
            "& Chất lượng: Đổi trả 100% trong vòng 12 tháng nếu có lỗi móp méo, rách, bục hoặc không đạt định lượng."
        )
        == 12
    )
    assert extract_warranty_months("Đổi trả trong 6 tháng nếu không đúng mẫu mã") == 6
    assert extract_warranty_months("Bảo hành 24 tháng, cam kết không trầy xước") == 24

    # Test payment deposit
    risk, _, risks = analyze_payment_terms("Đặt cọc 50% trước khi giao hàng")
    assert risk == "high"
    assert "50%" in risks[0]

    risk, _, risks = analyze_payment_terms("50 % đặt cọc")
    assert risk == "high"
    assert "50%" in risks[0]

    risk, _, risks = analyze_payment_terms("Tạm ứng: 45% giá trị hợp đồng")
    assert risk == "medium"
    assert "45%" in risks[0]

    risk, strengths, _ = analyze_payment_terms("Thanh toán 100% sau khi nghiệm thu")
    assert risk == "low"
    assert len(strengths) >= 1


def test_build_comparison_with_zero_budget(sample_pr, sample_quotations):
    from src.services.procurement.comparison import build_comparison

    _, pr = sample_pr
    _, quotes = sample_quotations
    # Set budget to 0 to test division by zero safety
    pr_zero = pr.model_copy(update={"estimated_budget": Decimal("0")})
    comparison = build_comparison(pr_zero, quotes)
    assert comparison is not None
    assert comparison.suppliers[0].budget_variance_percent == 0.0
