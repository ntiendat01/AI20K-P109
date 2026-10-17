"""Generate 6-month growth dataset for AI Procurement Agent (Procura).

Simulates realistic enterprise procurement growth over 6 months:
- Month -5: 5 PRs (Approved)
- Month -4: 8 PRs (Approved & Completed)
- Month -3: 12 PRs (Approved & Completed)
- Month -2: 16 PRs (Approved & Completed)
- Month -1: 22 PRs (Mostly Approved, some Pending Approval)
- Current Month: 28 PRs (Active pipeline: Awaiting, Comparing, Pending, Approved)

Total: ~91 PRs, ~210 Quotations, ~65 Purchase Orders.
All records pass strict Pydantic contract validation.
"""

from __future__ import annotations

import json
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath("."))

from src.domain.procurement.contracts import POStatus, PurchaseOrder
from src.domain.purchase_request import PRStatus, PurchaseRequest
from src.domain.quotation.confirmation import Quotation

PDF_MINH_KHANG_HASH = "0b81e6d325e6b87a004713d427ae1b14dd7e4da4cadbdca97fc05b080afed044"
PDF_HOANG_GIA_HASH = "a4db23a7fcb89220e33735bed19d6651a4f86181e2cf6c42d7185831fb96f53a"
PDF_AN_PHAT_HASH = "140c5f96d8fbccc19a0bb0fd1bb7537b19d2249ea93d7ae46ea405a53729352f"

SUPPLIERS = [
    {
        "id": "ncc-hoang-gia",
        "name": "Công Ty CP Sản Xuất Nhựa & Bao Bì Hoàng Gia",
        "hash": PDF_HOANG_GIA_HASH,
        "filename": "Báo Giá - Nhựa Hoàng Gia.pdf",
        "base_price_factor": 0.98,
        "lead_time": 4,
        "warranty": 18,
    },
    {
        "id": "ncc-minh-khang",
        "name": "Công Ty TNHH Sản Xuất Bao Bì Minh Khang",
        "hash": PDF_MINH_KHANG_HASH,
        "filename": "Báo Giá - Bao Bì Minh Khang.pdf",
        "base_price_factor": 1.00,
        "lead_time": 3,
        "warranty": 12,
    },
    {
        "id": "ncc-an-phat",
        "name": "Công Ty TNHH TM & VLĐG An Phát",
        "hash": PDF_AN_PHAT_HASH,
        "filename": "Báo Giá - Bao Bì An Phát.pdf",
        "base_price_factor": 1.03,
        "lead_time": 2,
        "warranty": 12,
    },
]

CATEGORIES = [
    {
        "name": "Bao bì đóng gói",
        "product": "Xốp khí bọc hàng chống sốc khổ 0.5m x 1m, bóng khí 10mm",
        "uom": "Mét",
        "unit_price": 2500,
        "typical_qty": 5000,
    },
    {
        "name": "Thiết bị văn phòng",
        "product": "Máy in laser đa chức năng HP LaserJet Pro",
        "uom": "Bộ",
        "unit_price": 7000000,
        "typical_qty": 5,
    },
    {
        "name": "Vật tư tiêu hao sản xuất",
        "product": "Găng tay bảo hộ phủ PU chống tĩnh điện",
        "uom": "Đôi",
        "unit_price": 18000,
        "typical_qty": 1000,
    },
    {
        "name": "Thiết bị tin học & IT",
        "product": "Màn hình đồ họa chuyên dụng 27 inch 4K",
        "uom": "Cái",
        "unit_price": 8500000,
        "typical_qty": 10,
    },
    {
        "name": "Hóa chất công nghiệp",
        "product": "Dung dịch tẩy rửa công nghiệp bề mặt kim loại",
        "uom": "Lít",
        "unit_price": 45000,
        "typical_qty": 500,
    },
    {
        "name": "Vật liệu bảo hộ",
        "product": "Màng cuốn pallet PE co giãn bảo vệ hàng hóa",
        "uom": "Cuộn",
        "unit_price": 125000,
        "typical_qty": 200,
    },
]

# Random seed for reproducible generation
random.seed(42)

NOW = datetime.now(UTC)
TODAY = NOW.date()

MONTH_PLANS = [
    {"month_idx": -5, "days_ago_range": (150, 180), "count": 5, "statuses": ["approved"] * 5},
    {"month_idx": -4, "days_ago_range": (120, 150), "count": 8, "statuses": ["approved"] * 8},
    {"month_idx": -3, "days_ago_range": (90, 120), "count": 12, "statuses": ["approved"] * 12},
    {"month_idx": -2, "days_ago_range": (60, 90), "count": 16, "statuses": ["approved"] * 16},
    {
        "month_idx": -1,
        "days_ago_range": (30, 60),
        "count": 22,
        "statuses": ["approved"] * 18 + ["pending_approval"] * 4,
    },
    {
        "month_idx": 0,
        "days_ago_range": (1, 30),
        "count": 28,
        "statuses": (
            ["awaiting_quotation"] * 6
            + ["comparing"] * 10
            + ["pending_approval"] * 6
            + ["approved"] * 6
        ),
    },
]


def generate_dataset():
    purchase_requests = []
    quotations = []
    purchase_orders = []

    pr_counter = 1

    for plan in MONTH_PLANS:
        min_days, max_days = plan["days_ago_range"]
        statuses = plan["statuses"]

        for status_str in statuses:
            code = f"PR-2026-{pr_counter:03d}"
            pr_id = f"pr-seed-{pr_counter:03d}"

            days_ago = random.randint(min_days, max_days)
            created_at = NOW - timedelta(days=days_ago, hours=random.randint(1, 10))
            updated_at = created_at + timedelta(hours=random.randint(2, 24))

            # Delivery due date
            if status_str == "approved" and days_ago > 30:
                # Past delivery
                delivery_due = (created_at + timedelta(days=14)).date()
            else:
                # Future delivery for recent PRs
                delivery_due = TODAY + timedelta(days=random.randint(5, 20))

            cat = random.choice(CATEGORIES)
            qty = cat["typical_qty"]
            estimated_budget = int(cat["unit_price"] * qty * random.uniform(1.05, 1.15))

            items = [
                {
                    "item_id": f"item-{pr_counter:03d}-1",
                    "order_index": 1,
                    "product_name": cat["product"],
                    "quantity": qty,
                    "unit": cat["uom"],
                    "notes": "Tiêu chuẩn kiểm định chất lượng đầy đủ",
                }
            ]

            # Determine number of quotes based on status
            if status_str == "awaiting_quotation":
                quote_count = 0
            elif status_str == "comparing":
                quote_count = random.choice([2, 3])
            else:
                # pending_approval or approved
                quote_count = random.choice([2, 3])

            pr_quotes = []
            selected_suppliers = random.sample(SUPPLIERS, quote_count)

            winning_quote_id = None
            winning_supplier = None
            winning_total = None

            for s_idx, sup in enumerate(selected_suppliers):
                quote_id = f"quote-{pr_counter:03d}-{s_idx + 1}"
                unit_price = int(cat["unit_price"] * sup["base_price_factor"] * random.uniform(0.98, 1.02))
                subtotal = unit_price * qty
                vat_rate = 0.08
                tax_amount = int(subtotal * vat_rate)
                total_with_tax = subtotal + tax_amount

                if s_idx == 0 or (winning_total and total_with_tax < winning_total):
                    winning_quote_id = quote_id
                    winning_supplier = sup
                    winning_total = total_with_tax

                q_created = created_at + timedelta(hours=random.randint(1, 6))
                q_confirmed = q_created + timedelta(hours=random.randint(2, 8))

                quote_record = {
                    "id": quote_id,
                    "pr_id": pr_id,
                    "supplier_id": sup["id"],
                    "supplier_name": sup["name"],
                    "source_filename": sup["filename"],
                    "source_hash": sup["hash"],
                    "source_content_type": "application/pdf",
                    "source_path": f"data/uploads/{pr_id}/{sup['hash']}.pdf",
                    "extraction_version": 4,
                    "delivery_time": f"{sup['lead_time']} ngày làm việc sau xác nhận đơn hàng",
                    "payment_terms": "Thanh toán trong 30 ngày sau khi nhận hàng và hóa đơn hợp lệ",
                    "warranty": f"{sup['warranty']} tháng",
                    "currency": "VND",
                    "items": [
                        {
                            "product_name": cat["product"],
                            "product_code": f"SKU-{cat['uom'][:2]}-{random.randint(100, 999)}",
                            "unit": cat["uom"],
                            "quantity": qty,
                            "unit_price": str(unit_price),
                            "line_total": str(subtotal),
                            "matched_pr_item_id": f"item-{pr_counter:03d}-1",
                            "match_status": None,
                        }
                    ],
                    "status": "confirmed",
                    "extraction_warnings": [],
                    "cache_hit": False,
                    "created_at": q_created.isoformat(),
                    "confirmed_at": q_confirmed.isoformat(),
                    "vat_rate": str(vat_rate),
                    "vat_included": False,
                    "shipping_fee": "0",
                    "lead_time_days": sup["lead_time"],
                    "warranty_months": sup["warranty"],
                    "goods_total_including_tax": str(total_with_tax),
                    "shipping_total_including_tax": "0",
                    "extraction_mode": "agent",
                    "agent_extractions": [],
                }
                pr_quotes.append(quote_record)
                quotations.append(quote_record)

            po_id = None
            if status_str == "approved" and winning_supplier:
                po_id = f"po-seed-{pr_counter:03d}"
                po_code = f"PO-2026-{pr_counter:03d}"
                po_created = updated_at + timedelta(hours=random.randint(2, 6))

                po_record = {
                    "id": po_id,
                    "code": po_code,
                    "pr_id": pr_id,
                    "pr_code": code,
                    "quotation_id": winning_quote_id,
                    "supplier_name": winning_supplier["name"],
                    "items": [
                        {
                            "product_name": cat["product"],
                            "product_code": f"SKU-{cat['uom'][:2]}-001",
                            "unit": cat["uom"],
                            "quantity": qty,
                            "unit_price": str(int(winning_total / 1.08 / qty)),
                            "line_total": str(int(winning_total / 1.08)),
                        }
                    ],
                    "total_amount": f"{winning_total:.2f}",
                    "currency": "VNĐ",
                    "delivery_time": f"{winning_supplier['lead_time']} ngày làm việc",
                    "payment_terms": "Thanh toán trong 30 ngày sau khi nghiệm thu",
                    "warranty": f"{winning_supplier['warranty']} tháng",
                    "status": "draft",
                    "approver_id": "user-manager-01",
                    "approver_name": "Trần Quang Huy",
                    "approved_at": po_created.isoformat(),
                    "manager_note": f"Phê duyệt lựa chọn {winning_supplier['name']}: đáp ứng ngân sách và bảo hành tốt.",
                    "created_at": po_created.isoformat(),
                    "subtotal": f"{int(winning_total / 1.08):.2f}",
                    "shipping_amount": "0.00",
                    "tax_amount": f"{winning_total - int(winning_total / 1.08):.2f}",
                    "prices_include_tax": False,
                    "recommendation_id": f"rec-{pr_counter:03d}",
                    "recommendation_version": 1,
                    "snapshot_revision": None,
                }
                purchase_orders.append(po_record)

            pr_record = {
                "id": pr_id,
                "tenant_id": "default-tenant",
                "code": code,
                "creator_id": "user-procurement-01",
                "creator_name": "Nguyễn Minh Anh",
                "category": cat["name"],
                "requested_quantity": qty,
                "requested_uom": cat["uom"],
                "target_currency": "VND",
                "estimated_budget": estimated_budget,
                "delivery_due_date": str(delivery_due),
                "metadata": None,
                "items": items,
                "status": status_str,
                "quotation_count": quote_count,
                "rejection_reason": None,
                "po_id": po_id,
                "version": 1,
                "created_at": created_at.isoformat(),
                "updated_at": updated_at.isoformat(),
            }
            purchase_requests.append(pr_record)
            pr_counter += 1

    return purchase_requests, quotations, purchase_orders


def main():
    print("Generating 6-month growth procurement dataset...")
    prs, quotes, pos = generate_dataset()

    print(f"Generated: {len(prs)} PRs, {len(quotes)} Quotations, {len(pos)} POs.")

    # Validate all models
    print("Validating with Pydantic domain models...")
    for pr in prs:
        PurchaseRequest.model_validate(pr)
    for q in quotes:
        Quotation.model_validate(q)
    for po in pos:
        PurchaseOrder.model_validate(po)
    print("All records successfully validated!")

    # Write to seeds/data
    data_dir = Path("seeds/data")
    data_dir.mkdir(parents=True, exist_ok=True)

    with (data_dir / "purchase_requests.json").open("w", encoding="utf-8") as f:
        json.dump(prs, f, ensure_ascii=False, indent=2)

    with (data_dir / "quotations.json").open("w", encoding="utf-8") as f:
        json.dump(quotes, f, ensure_ascii=False, indent=2)

    with (data_dir / "purchase_orders.json").open("w", encoding="utf-8") as f:
        json.dump(pos, f, ensure_ascii=False, indent=2)

    print("Successfully written 6-month growth dataset to seeds/data/!")


if __name__ == "__main__":
    main()
