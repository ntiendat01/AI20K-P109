"""Generated PDF fixtures exercise the extraction pipeline and batch API."""

import json
from datetime import date, timedelta

import fitz
import pytest

from src.infrastructure.documents.detector import detect_pdf_type
from src.infrastructure.documents.pdf_extractor import ExtractedDocument, PDFTextExtractor
from src.infrastructure.documents.quotation_parser import parse_number, parse_quotation
from src.infrastructure.documents.service import process_pdf
from src.main import app
from src.domain.quotation.extraction import ExtractedQuotation as Quotation
from src.domain.quotation.extraction import ExtractionStatus
from src.domain.quotation.extraction import ExtractedPage
from src.infrastructure.ocr.contracts import OCRLine, OCRPage
from src.infrastructure.repositories.purchase_requests import PurchaseRequestRepository, get_pr_repository

QUOTE = """Supplier: ABC Technology
Quotation No: ABC-2026-0918
Quotation Date: 2026-09-18
Currency: VND
Item name | Description | Qty | Unit | Unit Price | Amount
Dell Latitude 5450 Laptop | Ultra 5 / 16GB / 512GB SSD | 10 | pcs | 24,500,000 | 245,000,000
Subtotal: 245,000,000
VAT 10%: 24,500,000
Grand Total: 269,500,000
"""


def pdf_with_text(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page(width=800, height=900)
    for index, line in enumerate(text.splitlines()):
        page.insert_text((30, 40 + index * 25), line, fontsize=11)
    content = document.tobytes()
    document.close()
    return content


def table_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=700, height=500)
    page.insert_text((30, 30), "Supplier: Table Company")
    x = [30, 270, 350, 480, 650]
    y = [60, 90, 120]
    for xx in x:
        page.draw_line((xx, y[0]), (xx, y[-1]))
    for yy in y:
        page.draw_line((x[0], yy), (x[-1], yy))
    for xx, value in zip(x[:-1], ["Item name", "Qty", "Unit Price", "Amount"], strict=True):
        page.insert_text((xx + 5, 80), value, fontsize=9)
    for xx, value in zip(x[:-1], ["Dell Laptop", "2", "24.500.000", "49.000.000"], strict=True):
        page.insert_text((xx + 5, 110), value, fontsize=9)
    content = document.tobytes()
    document.close()
    return content


def scanned_pdf() -> bytes:
    original = fitz.open(stream=pdf_with_text(QUOTE), filetype="pdf")
    image = original[0].get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
    original.close()
    scanned = fitz.open()
    page = scanned.new_page(width=800, height=900)
    page.insert_image(page.rect, stream=image)
    content = scanned.tobytes()
    scanned.close()
    return content


def test_clean_text_pdf_preserves_raw_values_and_skips_ocr(monkeypatch):
    monkeypatch.setattr("src.infrastructure.documents.pdf_extractor.ocr_page_data", lambda page: pytest.fail("OCR called for text PDF"))
    result = process_pdf("quote.pdf", pdf_with_text(QUOTE))
    assert result.status == ExtractionStatus.COMPLETED
    assert result.document_type == "text"
    assert isinstance(result.quotation, Quotation)
    assert result.quotation.supplier_name == "ABC Technology"
    assert result.quotation.quotation_number == "ABC-2026-0918"
    assert result.quotation.quotation_date == "2026-09-18"
    assert result.quotation.items[0].raw_name == "Dell Latitude 5450 Laptop"
    assert result.quotation.items[0].raw_description == "Ultra 5 / 16GB / 512GB SSD"
    assert result.quotation.items[0].total_price == 245_000_000
    assert result.quotation.vat_rate == 10
    assert result.pages[0].page_number == 1
    assert result.pages[0].method == "text"


def test_table_pdf_extracts_line_items():
    result = process_pdf("table.pdf", table_pdf())
    assert result.document_type == "text"
    assert isinstance(result.quotation, Quotation)
    assert len(result.quotation.items) == 1
    assert result.quotation.items[0].raw_name == "Dell Laptop"
    assert result.quotation.items[0].unit_price == 24_500_000


def test_vietnamese_quote_table_maps_mat_hang_quy_cach_to_item_name():
    document = ExtractedDocument(
        document_type="text",
        pages=[ExtractedPage(page_number=1, method="text", text="Tiền tệ: VND")],
        tables=[
            (
                1,
                [
                    ["STT", "Mặt hàng / Quy cách", "Nhãn hiệu", "SL", "ĐVT", "Đơn giá (VND)", "Thành tiền (VND)"],
                    ["1", "Thép thanh vằn D16", "Việt Nhật", "20", "tấn", "15.050.000", "301.000.000"],
                ],
            )
        ],
    )

    quotation = parse_quotation(document)

    assert quotation.currency == "VND"
    assert [
        (item.raw_name, item.quantity, item.unit, item.unit_price, item.total_price) for item in quotation.items
    ] == [("Thép thanh vằn D16", 20, "tấn", 15_050_000, 301_000_000)]


def test_scanned_pdf_uses_ocr_and_mixed_detection(tmp_path, monkeypatch):
    calls = []

    def fake_ocr(page):
        calls.append(page.number)
        return OCRPage(page_number=1, raw_text=QUOTE)

    monkeypatch.setattr("src.infrastructure.documents.pdf_extractor.ocr_page_data", fake_ocr)
    scan = scanned_pdf()
    path = tmp_path / "scan.pdf"
    path.write_bytes(scan)
    assert detect_pdf_type(str(path)) == "scanned"
    result = process_pdf("scan.pdf", scan)
    assert calls == [0]
    assert result.document_type == "scanned"
    assert result.pages[0].method == "ocr"
    assert result.quotation.items[0].raw_name == "Dell Latitude 5450 Laptop"

    document = fitz.open(stream=pdf_with_text(QUOTE), filetype="pdf")
    scan_document = fitz.open(stream=scan, filetype="pdf")
    document.insert_pdf(scan_document)
    path.write_bytes(document.tobytes())
    document.close()
    scan_document.close()
    assert detect_pdf_type(str(path)) == "mixed"


def test_pdf_text_extractor_preserves_ocr_line_confidence(tmp_path, monkeypatch):
    path = tmp_path / "scan.pdf"
    path.write_bytes(scanned_pdf())
    monkeypatch.setattr(
        "src.infrastructure.documents.pdf_extractor.ocr_page_data",
        lambda _page: OCRPage(
            page_number=1,
            raw_text="Laptop",
            lines=[OCRLine(text="Laptop", confidence=0.97)],
        ),
    )

    payload = json.loads(PDFTextExtractor().extract_text(str(path)))

    assert payload["pages"] == [
        {
            "page_number": 1,
            "raw_text": "Laptop",
            "lines": [{"text": "Laptop", "confidence": 0.97}],
        }
    ]


def test_missing_fields_remain_null():
    result = process_pdf(
        "partial.pdf",
        pdf_with_text("Supplier: ABC Technology\nItem name | Qty | Unit Price | Amount\nLaptop | 2 | unknown |"),
    )
    assert result.quotation.quotation_date is None
    assert result.quotation.grand_total is None
    assert result.quotation.items[0].unit_price is None
    assert result.quotation.items[0].total_price is None
    assert result.status == ExtractionStatus.NEEDS_REVIEW


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("24,500,000", 24_500_000),
        ("24.500.000", 24_500_000),
        ("24 500 000", 24_500_000),
        ("24.500.000,00", 24_500_000),
        ("1,234.50", 1234.5),
        ("12.34.56", None),
        ("unknown", None),
    ],
)
def test_number_formats(raw, expected):
    assert parse_number(raw) == expected


@pytest.fixture
def repository(tmp_path):
    repo = PurchaseRequestRepository(tmp_path / "prs.json")
    app.dependency_overrides[get_pr_repository] = lambda: repo
    yield repo
    app.dependency_overrides.pop(get_pr_repository, None)


@pytest.mark.asyncio
async def test_batch_extracts_independently_and_reports_corruption(client, repository):
    login = await client.post(
        "/api/v1/auth/login", json={"email": "anhnm@dotcom.vn", "password": "Purchase123!"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    created = await client.post(
        "/api/v1/prs",
        headers=headers,
        json={
            "code": "PR-EXTRACT-001",
            "category": "Thiết bị máy tính",
            "quantity": 2,
            "estimated_budget": "50000000",
            "delivery_due_date": (date.today() + timedelta(days=10)).isoformat(),
        },
    )
    request_id = created.json()["id"]
    response = await client.post(
        f"/api/v1/prs/{request_id}/extract",
        headers=headers,
        files=[
            ("files[]", ("a.pdf", pdf_with_text(QUOTE), "application/pdf")),
            ("files[]", ("b.pdf", table_pdf(), "application/pdf")),
            ("files[]", ("broken.pdf", b"%PDF-corrupt", "application/pdf")),
        ],
    )
    assert response.status_code == 200
    results = response.json()["quotations"]
    assert [item["status"] for item in results] == ["completed", "completed", "failed"]
    assert results[0]["quotation"]["items"][0]["raw_name"] == "Dell Latitude 5450 Laptop"
    assert results[2]["error"]
