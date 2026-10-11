import json
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import fitz
import pytest
from pypdf import PdfWriter

from src.extraction.pdf_extractor import ExtractedDocument
from src.main import app
from src.models.extracted_quotation import ExtractedPage
from src.models.quotation.confirmation import Quotation
from src.models.schemas import QuotationConfirmation
from src.models_v1.quotation.extraction import (
    ExtractedFieldValue,
    ExtractedItemField,
    ExtractionDraftPayload,
    FieldSource,
)
from src.services.procurement.purchase_requests import PurchaseRequestRepository, get_pr_repository
from src.services.quotation.intake import extract_for_quotation, resume_confirmation
from src.services.quotation.parser import extract_quotation
from src.services.quotation.repository import QuotationRepository, get_quotation_repository

PROCUREMENT_CREDENTIALS = {
    "email": "purchasing@vinuni.edu.vn",
    "password": "Purchase123!",
}
MANAGER_CREDENTIALS = {
    "email": "manager@vinuni.edu.vn",
    "password": "Manager123!",
}

SYNTHETIC_QUOTE = """Nhà cung cấp: Công ty Thiết bị Sao Mai
Thời gian giao hàng: 7 ngày làm việc
Điều khoản thanh toán: Thanh toán trong 30 ngày
Mã hàng | Tên hàng | Số lượng | Đơn giá | Thành tiền
LT-01 | Laptop Dell Latitude | 2 | 25000000 | 50000000
MN-02 | Màn hình Dell 24 inch | 2 | 5000000 | 10000000
"""

VERTICAL_PDF_TEXT = """QUOTATION / BÁO GIÁ
Supplier
VietTech Solutions JSC
Currency
VND
No.
Item / Description
Qty
Unit
Unit Price
Amount
1
Dell Latitude 5450 Laptop
Latitude 5450 / Ultra 5 125U / RAM 16GB / SSD 512GB
10
bộ
23,900,000
239,000,000
2
Dell P2425H Monitor
P2425H 24in Full HD IPS, HDMI/DP
10
cái
4,950,000
49,500,000
Subtotal
289,000,000
Commercial Terms
• Delivery: within 7–14 working days after purchase order.
• Payment: 50% advance, 50% after delivery and acceptance.
"""


def test_extracts_supplier_and_items_from_vertical_pdf_text_layout():
    """The PDFs used in the demo emit visual table columns on separate lines."""
    extracted = extract_quotation(VERTICAL_PDF_TEXT.encode(), ".txt")

    assert extracted.supplier_name == "VietTech Solutions JSC"
    assert extracted.currency == "VND"
    assert extracted.delivery_time == "within 7–14 working days after purchase order."
    assert extracted.payment_terms == "50% advance, 50% after delivery and acceptance."
    assert len(extracted.items) == 2
    assert (
        extracted.items[0].product_name
        == "Dell Latitude 5450 Laptop Latitude 5450 / Ultra 5 125U / RAM 16GB / SSD 512GB"
    )
    assert extracted.items[0].unit == "bộ"
    assert extracted.items[0].quantity == 10
    assert extracted.items[0].unit_price == 23_900_000
    assert extracted.items[0].line_total == 239_000_000


def test_repository_reads_legacy_currency_evidence_without_changing_other_records(tmp_path):
    """One legacy snapshot must not make the quotation collection unreadable."""
    repository = QuotationRepository(tmp_path / "quotations.json", tmp_path / "uploads")
    source_path = "uploads/legacy/bao-gia.pdf"
    quotation = Quotation(
        id="legacy-quote",
        pr_id="legacy-pr",
        supplier_name="Nhà cung cấp cũ",
        source_filename="bao-gia.pdf",
        source_hash="legacy-hash",
        source_path=source_path,
        source_content_type="application/pdf",
    ).model_dump(mode="json")
    quotation["source_path"] = source_path
    quotation["currency"] = {
        "value": "VND",
        "confidence": "0.99",
        "source": {"document_id": "legacy-doc", "page_number": 1, "block_id": "currency"},
    }
    repository.storage_path.write_text(json.dumps([quotation]), encoding="utf-8")

    loaded = repository.list_for_pr("legacy-pr")

    assert len(loaded) == 1
    assert loaded[0].currency == "VND"


def test_agent_intake_projects_v1_draft_to_legacy_review_contract(tmp_path):
    """The v1 evidence wrapper must not leak into the legacy review record."""
    source_path = tmp_path / "quote.pdf"
    source_path.write_bytes(b"%PDF-1.7 fixture")
    quotation = Quotation(
        id="agent-quote",
        pr_id="agent-pr",
        supplier_name="Tên từ file",
        source_filename="quote.pdf",
        source_hash="agent-hash",
        source_path=str(source_path),
        source_content_type="application/pdf",
    )

    class OCR:
        def extract_text(self, path):
            del path
            return "OCR text"

    class Extractor:
        def extract_items(self, text, path):
            del text, path
            return [
                {
                    "supplier": "Nhà cung cấp A",
                    "item_name": "Thép thanh",
                    "quantity": 10,
                    "unit": "cây",
                    "unit_price": 150000,
                    "currency": "VND",
                    "vat_rate": 0.1,
                    "vat_included": False,
                    "lead_time_days": 7,
                    "warranty_months": 12,
                    "page_number": 1,
                    "confidence_score": 0.95,
                }
            ]

    extracted, agent_lines, _ = extract_for_quotation(quotation, ocr=OCR(), extractor=Extractor())

    assert extracted.supplier_name == "Nhà cung cấp A"
    assert extracted.currency == "VND"
    assert [(item.product_name, item.quantity, item.unit_price) for item in extracted.items] == [
        ("Thép thanh", 10, 150000)
    ]
    assert agent_lines[0]["currency"] == "VND"
    assert agent_lines[0]["item_name"] == "Thép thanh"
    assert agent_lines[0]["source"]["page_number"] == 1


def test_agent_intake_keeps_confirmable_lines_in_lockstep_with_agent_extractions(tmp_path, monkeypatch):
    """Unsupported legacy rows must warn, not make Buyer confirmation impossible."""
    source_path = tmp_path / "quote.pdf"
    source_path.write_bytes(b"%PDF-1.7 fixture")
    quotation = Quotation(
        id="agent-lockstep",
        pr_id="agent-pr",
        supplier_name="NCC thép",
        source_filename="quote.pdf",
        source_hash="agent-hash",
        source_path=str(source_path),
        source_content_type="application/pdf",
    )

    def field(value, block_id):
        return ExtractedFieldValue(
            value=value,
            confidence=Decimal("0.95"),
            source=FieldSource(document_id="agent-lockstep", page_number=1, block_id=block_id),
        )

    draft = ExtractionDraftPayload(
        supplier_name=field("NCC thép", "supplier"),
        currency=field("VND", "currency"),
        items=[
            ExtractedItemField(
                source_item_id="item-valid",
                product_name=field("Thép D16", "name-valid"),
                unit=field("tấn", "unit-valid"),
                quantity=field("2", "quantity-valid"),
                unit_price=field("15000000", "price-valid"),
            ),
            ExtractedItemField(
                source_item_id="item-fractional",
                product_name=field("Thép D10", "name-fractional"),
                unit=field("tấn", "unit-fractional"),
                quantity=field("2.5", "quantity-fractional"),
                unit_price=field("12000000", "price-fractional"),
            ),
            ExtractedItemField(
                source_item_id="item-no-price",
                product_name=field("Thép D8", "name-no-price"),
                unit=field("tấn", "unit-no-price"),
                quantity=field("2", "quantity-no-price"),
                unit_price=field(None, "price-no-price"),
            ),
        ],
    )

    class Graph:
        def invoke(self, state, config):
            del state, config
            return {"raw_extractions": [draft.model_dump(mode="json")]}

    monkeypatch.setattr("src.services.quotation.intake.intake_graph", lambda **_: Graph())

    extracted, agent_lines, _ = extract_for_quotation(quotation)

    assert [item.product_name for item in extracted.items] == ["Thép D16"]
    assert [line["extraction_id"] for line in agent_lines] == ["item-valid"]
    assert any("item-fractional" in warning and "số lượng lẻ" in warning for warning in extracted.warnings)
    assert any("item-no-price" in warning and "thiếu" in warning for warning in extracted.warnings)

    confirmation = QuotationConfirmation(
        supplier_name="NCC thép",
        items=[
            {
                "product_name": "Thép D16",
                "unit": "tấn",
                "quantity": 2,
                "unit_price": "15000000",
                "line_total": "30000000",
            }
        ],
        currency="VND",
        vat_rate="0.1",
        vat_included=False,
        shipping_fee="0",
        lead_time_days=7,
        warranty_months=12,
    )
    confirmed_lines = resume_confirmation(quotation.model_copy(update={"agent_extractions": agent_lines}), confirmation)

    assert len(confirmed_lines) == len(extracted.items) == 1
    assert confirmed_lines[0]["extraction_id"] == "item-valid"


def _pdf_with_text(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page(width=900, height=900)
    for index, line in enumerate(text.splitlines()):
        page.insert_text((30, 40 + index * 24), line, fontsize=11)
    content = document.tobytes()
    document.close()
    return content


def test_upload_parser_uses_pymupdf_and_maps_six_column_rows():
    """The active upload path must preserve the unit column in supplier PDFs."""
    source = """Supplier VietTech Solutions JSC
Currency VND
Delivery: within 7 to 14 working days after purchase order.
Payment: 50% advance, 50% after delivery and acceptance.
No. | Item / Description | Qty | Unit | Unit Price | Amount
1 | Dell Latitude 5450 Laptop | 10 | pcs | 23,900,000 | 239,000,000
2 | Dell P2425H Monitor | 10 | pcs | 4,950,000 | 49,500,000
"""
    extracted = extract_quotation(_pdf_with_text(source), ".pdf")

    assert extracted.supplier_name == "VietTech Solutions JSC"
    assert extracted.currency == "VND"
    assert extracted.delivery_time == "within 7 to 14 working days after purchase order."
    assert extracted.payment_terms == "50% advance, 50% after delivery and acceptance."
    assert [
        (item.product_name, item.quantity, item.unit, item.unit_price, item.line_total) for item in extracted.items
    ] == [
        ("Dell Latitude 5450 Laptop", 10, "pcs", 23_900_000, 239_000_000),
        ("Dell P2425H Monitor", 10, "pcs", 4_950_000, 49_500_000),
    ]


def test_multi_page_price_list_keeps_rows_without_quantity_or_line_total(monkeypatch):
    """Catalogues publish unit prices, not order rows; they must remain reviewable."""
    header = ["STT", "TÊN SẢN PHẨM", "QUY CÁCH / THÔNG SỐ", "ĐVT", "ĐƠN GIÁ BÁN LẺ (VNĐ)"]
    document = ExtractedDocument(
        document_type="text",
        pages=[
            ExtractedPage(
                page_number=1,
                method="text",
                text="CÔNG TY CỔ PHẦN BAO BÌ AN PHÁT\nBẢNG GIÁ THAM KHẢO\nCurrency: VNĐ",
            ),
            ExtractedPage(page_number=2, method="text", text="BẢNG GIÁ THAM KHẢO - trang 2"),
        ],
        tables=[
            (1, [header, ["1", "Thùng carton 3 lớp", "18x12x10 cm", "Thùng", "2.500"]]),
            (2, [header, ["2", "Băng keo OPP", "Khổ 4.8cm", "Cây", "62.000"]]),
        ],
    )
    monkeypatch.setattr("src.services.quotation.parser.extract_pdf", lambda content: document)

    extracted = extract_quotation(b"%PDF-catalog", ".pdf")

    assert extracted.supplier_name == "CÔNG TY CỔ PHẦN BAO BÌ AN PHÁT"
    assert extracted.currency == "VNĐ"
    assert [
        (item.product_name, item.unit, item.quantity, item.unit_price, item.line_total) for item in extracted.items
    ] == [
        ("Thùng carton 3 lớp 18x12x10 cm", "Thùng", 1, 2500, 2500),
        ("Băng keo OPP Khổ 4.8cm", "Cây", 1, 62000, 62000),
    ]
    assert any("số lượng mặc định là 1" in warning for warning in extracted.warnings)


@pytest.mark.asyncio
async def test_upload_pdf_uses_pymupdf_extraction_pipeline(client, repositories):
    headers = await procurement_headers(client)
    request_id = (await create_pr(client, headers)).json()["id"]
    source = """Supplier VietTech Solutions JSC
Currency VND
Delivery: within 7 to 14 working days after purchase order.
Payment: 50% advance, 50% after delivery and acceptance.
No. | Item / Description | Qty | Unit | Unit Price | Amount
1 | Dell Latitude 5450 Laptop | 10 | pcs | 23,900,000 | 239,000,000
"""

    response = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        files={"file": ("viettech.pdf", _pdf_with_text(source), "application/pdf")},
        headers=headers,
    )

    assert response.status_code == 201
    draft = response.json()
    assert draft["supplier_name"] == "VietTech Solutions JSC"
    assert draft["currency"] == "VND"
    assert draft["extraction_warnings"] == []
    assert draft["items"] == [
        {
            "product_name": "Dell Latitude 5450 Laptop",
            "product_code": "",
            "unit": "pcs",
            "quantity": 10,
            "unit_price": "23900000.0",
            "line_total": "239000000.0",
        }
    ]


@pytest.fixture
def repositories(tmp_path):
    pr_repository = PurchaseRequestRepository(tmp_path / "purchase_requests.json")
    quotation_repository = QuotationRepository(tmp_path / "quotations.json", tmp_path / "uploads")
    app.dependency_overrides[get_pr_repository] = lambda: pr_repository
    app.dependency_overrides[get_quotation_repository] = lambda: quotation_repository
    yield pr_repository, quotation_repository
    app.dependency_overrides.pop(get_pr_repository, None)
    app.dependency_overrides.pop(get_quotation_repository, None)


async def procurement_headers(client):
    response = await client.post("/api/v1/auth/login", json=PROCUREMENT_CREDENTIALS)
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_pr(client, headers):
    payload = {
        "code": "PR-QUOTE-001",
        "category": "Thiết bị công nghệ",
        "quantity": 4,
        "estimated_budget": "60000000",
        "delivery_due_date": (date.today() + timedelta(days=10)).isoformat(),
    }
    return await client.post("/api/v1/prs", json=payload, headers=headers)


@pytest.mark.asyncio
async def test_upload_extract_edit_and_confirm_quotation(client, repositories):
    headers = await procurement_headers(client)
    created_pr = await create_pr(client, headers)
    request_id = created_pr.json()["id"]

    upload = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        data={"supplier_name": "Sao Mai (từ biểu mẫu)"},
        files={"file": ("bao-gia.txt", SYNTHETIC_QUOTE.encode(), "text/plain")},
        headers=headers,
    )

    assert upload.status_code == 201
    draft = upload.json()
    assert draft["status"] == "unconfirmed"
    assert "source_path" not in draft
    assert draft["supplier_name"] == "Sao Mai (từ biểu mẫu)"
    assert draft["delivery_time"] == "7 ngày làm việc"
    assert draft["payment_terms"] == "Thanh toán trong 30 ngày"
    assert len(draft["items"]) == 2
    assert draft["items"][0]["product_name"] == "Laptop Dell Latitude"
    assert draft["items"][0]["unit_price"] == "25000000"

    confirm_payload = {
        "supplier_name": "Công ty Thiết bị Sao Mai",
        "delivery_time": "5 ngày làm việc",
        "payment_terms": "Thanh toán trong 30 ngày kể từ hóa đơn",
        "vat_rate": "0.1",
        "vat_included": False,
        "shipping_fee": "0",
        "lead_time_days": 5,
        "warranty_months": 12,
        "goods_total_including_tax": "64900000",
        "shipping_total_including_tax": "0",
        "items": [
            {
                "product_name": "Laptop Dell Latitude",
                "product_code": "LT-01",
                "quantity": 2,
                "unit_price": "24500000",
                "line_total": "49000000",
            },
            {
                "product_name": "Màn hình Dell 24 inch",
                "product_code": "MN-02",
                "quantity": 2,
                "unit_price": "5000000",
                "line_total": "10000000",
            },
        ],
    }
    confirmed = await client.post(f"/api/v1/quotations/{draft['id']}/confirm", json=confirm_payload, headers=headers)
    request = await client.get(f"/api/v1/prs/{request_id}", headers=headers)

    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["items"][0]["unit_price"] == "24500000"
    assert request.json()["status"] == "comparing"
    assert request.json()["quotation_count"] == 1


@pytest.mark.asyncio
async def test_fuzzy_matches_endpoint_returns_the_canonical_pr_name(client, repositories):
    headers = await procurement_headers(client)
    created_pr = await client.post(
        "/api/v1/prs",
        headers=headers,
        json={
            "code": "PR-FUZZY-001",
            "category": "Thiết bị công nghệ",
            "requested_quantity": 2,
            "requested_uom": "cái",
            "target_currency": "VND",
            "estimated_budget": "50000000",
            "delivery_due_date": (date.today() + timedelta(days=10)).isoformat(),
            "items": [
                {
                    "order_index": 0,
                    "product_name": "Thiết bị công nghệ",
                    "quantity": 2,
                    "unit": "cái",
                    "notes": "",
                }
            ],
        },
    )
    assert created_pr.status_code == 201
    request_id = created_pr.json()["id"]
    uploaded = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        files={"file": ("bao-gia.txt", SYNTHETIC_QUOTE.encode(), "text/plain")},
        headers=headers,
    )
    assert uploaded.status_code == 201

    confirmed = await client.post(
        f"/api/v1/quotations/{uploaded.json()['id']}/confirm",
        headers=headers,
        json={
            "supplier_name": "Công ty Thiết bị Sao Mai",
            "currency": "VND",
            "vat_rate": "0.1",
            "vat_included": False,
            "shipping_fee": "0",
            "lead_time_days": 5,
            "warranty_months": 12,
            "items": [
                {
                    "product_name": "Thiết bị công nghệ",
                    "quantity": 2,
                    "unit": "cái",
                    "unit_price": "24500000",
                    "line_total": "49000000",
                }
            ],
        },
    )
    matches = await client.get(f"/api/v1/prs/{request_id}/fuzzy-matches", headers=headers)

    assert confirmed.status_code == 200
    assert matches.status_code == 200
    result = matches.json()["results"][0]
    assert result["quote_item_id"] == f"{uploaded.json()['id']}:item:0"
    assert result["best_match"]["pr_item_name"] == "Thiết bị công nghệ"
    assert result["best_match"]["status"] == "auto_matched"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_field",
    ["vat_rate", "vat_included", "shipping_fee", "lead_time_days", "warranty_months"],
)
async def test_confirmation_rejects_each_missing_commercial_field(client, repositories, missing_field):
    headers = await procurement_headers(client)
    request_id = (await create_pr(client, headers)).json()["id"]
    upload = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        data={"supplier_name": "Sao Mai"},
        files={"file": ("bao-gia.txt", SYNTHETIC_QUOTE.encode(), "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 201
    payload = {
        "supplier_name": "Công ty Thiết bị Sao Mai",
        "currency": "VND",
        "vat_rate": "0.1",
        "vat_included": False,
        "shipping_fee": "0",
        "lead_time_days": 5,
        "warranty_months": 12,
        "items": [
            {
                "product_name": "Laptop Dell Latitude",
                "quantity": 2,
                "unit_price": "24500000",
                "line_total": "49000000",
            }
        ],
    }
    del payload[missing_field]

    response = await client.post(f"/api/v1/quotations/{upload.json()['id']}/confirm", json=payload, headers=headers)
    quotation = await client.get(f"/api/v1/quotations/{upload.json()['id']}", headers=headers)

    assert response.status_code == 422
    assert missing_field in response.text
    assert quotation.json()["status"] == "unconfirmed"


@pytest.mark.asyncio
async def test_same_file_uses_cached_extraction_and_source_is_protected(client, repositories):
    headers = await procurement_headers(client)
    request_id = (await create_pr(client, headers)).json()["id"]

    first = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        data={"supplier_name": "Nhà cung cấp A"},
        files={"file": ("quote.txt", SYNTHETIC_QUOTE.encode(), "text/plain")},
        headers=headers,
    )
    second = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        data={"supplier_name": "Nhà cung cấp B"},
        files={"file": ("quote-copy.txt", SYNTHETIC_QUOTE.encode(), "text/plain")},
        headers=headers,
    )
    source = await client.get(f"/api/v1/quotations/{first.json()['id']}/source", headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["cache_hit"] is True
    assert "source_path" not in first.json()
    assert source.status_code == 200
    assert source.content == SYNTHETIC_QUOTE.encode()


@pytest.mark.asyncio
async def test_manager_cannot_upload_or_read_quotations(client, repositories):
    procurement = await procurement_headers(client)
    request_id = (await create_pr(client, procurement)).json()["id"]
    manager_login = await client.post("/api/v1/auth/login", json=MANAGER_CREDENTIALS)
    manager_headers = {"Authorization": f"Bearer {manager_login.json()['access_token']}"}

    response = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        data={"supplier_name": "Nhà cung cấp A"},
        files={"file": ("quote.txt", SYNTHETIC_QUOTE.encode(), "text/plain")},
        headers=manager_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unsupported_file_is_rejected(client, repositories):
    headers = await procurement_headers(client)
    request_id = (await create_pr(client, headers)).json()["id"]

    response = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        data={"supplier_name": "Nhà cung cấp A"},
        files={"file": ("quote.xlsx", b"not-a-quote", "application/vnd.ms-excel")},
        headers=headers,
    )

    assert response.status_code == 415


@pytest.mark.asyncio
async def test_pdf_upload_returns_a_reviewable_extraction_draft(client, repositories):
    headers = await procurement_headers(client)
    request_id = (await create_pr(client, headers)).json()["id"]
    pdf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(pdf)

    response = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        data={"supplier_name": "Nhà cung cấp PDF"},
        files={"file": ("bao-gia.pdf", pdf.getvalue(), "application/pdf")},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["source_content_type"] == "application/pdf"
    assert response.json()["status"] == "unconfirmed"
    assert response.json()["extraction_warnings"]


@pytest.mark.asyncio
async def test_pdf_review_preview_renders_page_and_locates_extracted_row(client, repositories):
    headers = await procurement_headers(client)
    request_id = (await create_pr(client, headers)).json()["id"]
    source = """Supplier VietTech Solutions JSC
No. | Item / Description | Qty | Unit | Unit Price | Amount
1 | Dell Latitude 5450 Laptop | 10 | pcs | 23,900,000 | 239,000,000
"""
    uploaded = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        files={"file": ("viettech.pdf", _pdf_with_text(source), "application/pdf")},
        headers=headers,
    )
    quotation_id = uploaded.json()["id"]

    preview = await client.get(f"/api/v1/quotations/{quotation_id}/review-preview", headers=headers)
    page = await client.get(f"/api/v1/quotations/{quotation_id}/review-preview/pages/1", headers=headers)

    assert preview.status_code == 200
    assert preview.json()["pages"] == [{"number": 1, "width": 900.0, "height": 900.0}]
    assert preview.json()["matches"][0]["region"]["page"] == 1
    assert page.status_code == 200
    assert page.headers["content-type"] == "image/png"
    assert page.content.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_upload_without_supplier_name_uses_ocr_extracted_name(client, repositories):
    """Spec: 'không cần nhập tên NCC' — supplier_name trích xuất tự động từ file."""
    headers = await procurement_headers(client)
    request_id = (await create_pr(client, headers)).json()["id"]

    response = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        files={"file": ("bao-gia.txt", SYNTHETIC_QUOTE.encode(), "text/plain")},
        headers=headers,
    )

    assert response.status_code == 201
    draft = response.json()
    # OCR extracts "Công ty Thiết bị Sao Mai" from the synthetic quote
    assert draft["supplier_name"] == "Công ty Thiết bị Sao Mai"
    assert draft["status"] == "unconfirmed"


@pytest.mark.asyncio
async def test_unconfirmed_quotation_can_be_reextracted_with_current_parser(client, repositories):
    headers = await procurement_headers(client)
    request_id = (await create_pr(client, headers)).json()["id"]
    uploaded = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        files={"file": ("bao-gia.txt", VERTICAL_PDF_TEXT.encode(), "text/plain")},
        headers=headers,
    )

    response = await client.post(
        f"/api/v1/quotations/{uploaded.json()['id']}/re-extract",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["supplier_name"] == "VietTech Solutions JSC"
    assert len(response.json()["items"]) == 2
    assert response.json()["extraction_version"] == 4


@pytest.mark.asyncio
async def test_delete_pr_cascades_to_quotations_and_uploaded_sources(client, repositories):
    headers = await procurement_headers(client)
    pr_repository, quotation_repository = repositories
    request_id = (await create_pr(client, headers)).json()["id"]
    uploaded = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        files={"file": ("bao-gia.txt", SYNTHETIC_QUOTE.encode(), "text/plain")},
        headers=headers,
    )
    source_path = quotation_repository.get(uploaded.json()["id"]).source_path

    deleted = await client.delete(f"/api/v1/prs/{request_id}", headers=headers)
    missing_pr = await client.get(f"/api/v1/prs/{request_id}", headers=headers)

    assert deleted.status_code == 204
    assert pr_repository.get(request_id) is None
    assert quotation_repository.list_for_pr(request_id) == []
    assert not Path(source_path).exists()
    assert missing_pr.status_code == 404


@pytest.mark.asyncio
async def test_delete_one_quotation_removes_only_its_source_file(client, repositories):
    headers = await procurement_headers(client)
    pr_repository, quotation_repository = repositories
    request_id = (await create_pr(client, headers)).json()["id"]
    first = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        files={"file": ("first.txt", SYNTHETIC_QUOTE.encode(), "text/plain")},
        headers=headers,
    )
    second = await client.post(
        f"/api/v1/prs/{request_id}/quotations",
        files={"file": ("second.txt", VERTICAL_PDF_TEXT.encode(), "text/plain")},
        headers=headers,
    )
    first_id = first.json()["id"]
    second_id = second.json()["id"]
    first_source = quotation_repository.get(first_id).source_path
    second_source = quotation_repository.get(second_id).source_path

    deleted = await client.delete(f"/api/v1/quotations/{first_id}", headers=headers)
    remaining = await client.get(f"/api/v1/prs/{request_id}/quotations", headers=headers)

    assert deleted.status_code == 204
    assert not Path(first_source).exists()
    assert Path(second_source).exists()
    assert [quotation["id"] for quotation in remaining.json()] == [second_id]
    assert pr_repository.get(request_id).status.value == "awaiting_quotation"
