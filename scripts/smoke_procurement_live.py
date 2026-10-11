"""Anonymous live-provider E2E smoke; all business/evidence data stays in a temporary directory.

Run: python -m scripts.smoke_procurement_live --provider openai --output PATH
This deliberately calls the configured provider; never import or execute it from pytest.
"""

import argparse
import asyncio
import json
import logging
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pymupdf as fitz
from httpx import ASGITransport, AsyncClient

from src.core.config import get_settings
from src.main import app
from src.services import purchase_orders, purchase_requests, quotations

logger = logging.getLogger(__name__)
result_logger = logging.getLogger(f"{__name__}.result")
result_logger.setLevel(logging.INFO)
result_logger.propagate = False
result_handler = logging.StreamHandler(sys.stdout)
result_handler.setFormatter(logging.Formatter("%(message)s"))
result_logger.addHandler(result_handler)


def sample_pdf(name: str, price: int, days: int, warranty: int) -> bytes:
    with fitz.open() as document:
        document.new_page().insert_text(
            (72, 72),
            f"Supplier: {name}\nItem: Widget\nQuantity: 10 cai\nUnit price: {price} VND\n"
            f"Goods total before VAT: {price * 10} VND\nVAT: 10%, excluded from price\n"
            f"Shipping: 0 VND\nDelivery: {days} calendar days after order confirmation\n"
            f"Warranty: {warranty} months\nPayment: after acceptance",
        )
        return document.tobytes()


async def run(provider: str) -> dict:
    settings = get_settings()
    if provider == "openai" and not settings.openai_api_key.strip():
        raise ValueError("Cấu hình OPENAI_API_KEY trong .env trước khi chạy.")
    if provider == "openrouter" and not settings.openrouter_api_key.strip():
        raise ValueError("Cấu hình OPENROUTER_API_KEY trong .env trước khi chạy.")
    if provider == "groq" and not settings.groq_api_key:
        raise ValueError("Cấu hình GROQ_API_KEY trong .env trước khi chạy.")
    if provider == "qwen" and not settings.qwen_base_url:
        raise ValueError("Cấu hình QWEN_BASE_URL và model/key tương ứng trong .env trước khi chạy.")
    settings.llm_provider = provider
    settings.gemini_api_key = ""
    if provider != "openai":
        settings.openai_api_key = ""
    trace = []
    with tempfile.TemporaryDirectory(prefix="procura-live-") as directory:
        path = Path(directory)
        settings.chroma_persist_dir = str(path / "chroma")
        settings.procurement_workflow_path = path / "workflow.sqlite"
        settings.evaluation_database_path = path / "evaluation.sqlite"
        purchase_requests.repository = purchase_requests.PurchaseRequestRepository(path / "prs.json")
        quotations.repository = quotations.QuotationRepository(path / "quotes.json", path / "uploads")
        purchase_orders.repository = purchase_orders.PurchaseOrderRepository(path / "pos.json")
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://smoke", timeout=1200) as client:

                async def request(method: str, url: str, expected: int, **kwargs):
                    response = await client.request(method, url, **kwargs)
                    trace.append({"method": method, "path": url, "status": response.status_code})
                    if response.status_code != expected:
                        raise RuntimeError(f"{method} {url}: HTTP {response.status_code}")
                    return response.json()

                async def login(role):
                    data = await request(
                        "POST",
                        "/api/v1/auth/login",
                        200,
                        json={
                            "email": "purchasing@vinuni.edu.vn" if role == "buyer" else "manager@vinuni.edu.vn",
                            "password": "Purchase123!" if role == "buyer" else "Manager123!",
                        },
                    )
                    return {"Authorization": f"Bearer {data['access_token']}"}

                buyer, manager = await login("buyer"), await login("manager")
                pr = await request(
                    "POST",
                    "/api/v1/prs",
                    201,
                    headers=buyer,
                    json={
                        "code": "PR-LIVE-ANONYMOUS",
                        "category": "Anonymous Widget",
                        "quantity": 10,
                        "estimated_budget": "20000",
                        "delivery_due_date": (date.today() + timedelta(days=30)).isoformat(),
                    },
                )
                for name, price, days, warranty in [("Vendor A", 1000, 5, 12), ("Vendor B", 1200, 7, 24)]:
                    quote = await request(
                        "POST",
                        f"/api/v1/prs/{pr['id']}/quotations",
                        201,
                        headers=buyer,
                        data={"extraction_mode": "agent"},
                        files={"file": (f"{name}.pdf", sample_pdf(name, price, days, warranty), "application/pdf")},
                    )
                    if any(line.get("extraction_error") for line in quote["agent_extractions"]):
                        raise RuntimeError(
                            "Extraction provider chưa trả được dữ liệu hợp lệ; kiểm tra key/endpoint/model."
                        )
                    await request(
                        "POST",
                        f"/api/v1/quotations/{quote['id']}/confirm",
                        200,
                        headers=buyer,
                        json={
                            "supplier_name": name,
                            "currency": "VND",
                            "vat_rate": "0.1",
                            "vat_included": False,
                            "shipping_fee": "0",
                            "lead_time_days": days,
                            "warranty_months": warranty,
                            "delivery_time": f"{days} ngày lịch",
                            "payment_terms": "Sau nghiệm thu",
                            "goods_total_including_tax": str(price * 11),
                            "shipping_total_including_tax": "0",
                            "items": [
                                {
                                    "product_name": "Widget",
                                    "unit": "cái",
                                    "quantity": 10,
                                    "unit_price": price,
                                    "line_total": price * 10,
                                }
                            ],
                        },
                    )
                run = await request("POST", f"/api/v1/prs/{pr['id']}/analysis", 200, headers=buyer)
                if run["status"] != "awaiting_review":
                    return {"result": "not_ready", "provider": provider, "run": run, "trace": trace}
                if sorted(row["total_tco"] for row in run["tco_results"]) != [11000, 13200]:
                    raise RuntimeError("TCO khác đáp án tính tay 11000/13200 VND.")
                await request("POST", f"/api/v1/prs/{pr['id']}/submit-approval", 200, headers=buyer)
                review = await request(
                    "GET", f"/api/v1/recommendations/{run['recommendation_id']}/review", 200, headers=manager
                )
                payload = {
                    "feedback_id": "live-smoke",
                    "idempotency_key": "live-smoke",
                    "decision": "approve",
                    "recommendation_id": run["recommendation_id"],
                    "recommendation_version": run["recommendation_version"],
                    "note": "Anonymous automated smoke review",
                    "acknowledged_uncertainty_ids": review["critical_uncertainty_ids"],
                }
                feedback_url = f"/api/v1/recommendations/{run['recommendation_id']}/feedback"
                first = await request("POST", feedback_url, 200, headers=manager, json=payload)
                retry = await request("POST", feedback_url, 200, headers=manager, json=payload)
                po = first["po"]
                if po["id"] != retry["po"]["id"] or len(purchase_orders.repository.list()) != 1:
                    raise RuntimeError("Approval retry tạo PO khác nhau.")
                expected = {"Vendor A": 11000, "Vendor B": 13200}[po["supplier_name"]]
                if float(po["total_amount"]) != expected:
                    raise RuntimeError("Tổng PO không khớp báo giá nguồn đã xác nhận.")
                return {
                    "result": "passed",
                    "provider": provider,
                    "pr_id": pr["id"],
                    "analysis_id": run["analysis_id"],
                    "recommendation_id": run["recommendation_id"],
                    "recommendation_version": run["recommendation_version"],
                    "snapshot_revision": run["snapshot_revision"],
                    "po_id": po["id"],
                    "supplier": po["supplier_name"],
                    "total_amount": po["total_amount"],
                    "events": run["events"],
                    "trace": trace,
                }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["openai", "groq", "qwen", "openrouter"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = asyncio.run(run(args.provider))
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    result_logger.info(json.dumps({"result": report["result"], "provider": args.provider, "report": str(args.output)}))
    if report["result"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
