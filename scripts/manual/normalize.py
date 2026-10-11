"""Script chạy test tay độc lập cho Node normalize (src/agents/nodes/normalize.py).

Cách chạy:
    .venv\\Scripts\\python scripts/manual/normalize.py
    .venv\\Scripts\\python scripts/manual/normalize.py --custom path/to/custom_state.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Đảm bảo encoding utf-8 trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.nodes.normalize import normalize  # noqa: E402
from src.agents.state import ProcurementAgentState  # noqa: E402

logger = logging.getLogger(__name__)


def build_sample_cases() -> list[tuple[str, ProcurementAgentState]]:
    """Tạo các ca test điển hình để kiểm tra node normalize."""
    return [
        (
            "Test Case 1: Chuẩn hóa ĐVT (thùng -> cái) & Tiền tệ (USD -> VND)",
            {
                "pr_data": {
                    "pr_number": "PR-2026-001",
                    "quantity": 1000,
                    "target_uom": "cái",
                    "target_currency": "VND",
                },
                "raw_extractions": [
                    {
                        "extraction_id": "ext-001",
                        "source": {"filename": "quote_supplier_a.pdf", "page_number": 1},
                        "supplier_id": "NCC An Phát",
                        "item_name": "Bu lông M8x30 inox",
                        "unit_price": 50.0,  # 50 USD / thùng
                        "quantity": 5.0,  # 5 thùng
                        "unit": "thùng",  # 1 thùng = 200 cái
                        "currency": "USD",  # 1 USD = 25,400 VND
                        "vat_rate": 0.1,
                        "vat_included": False,
                        "surcharges": [
                            {
                                "kind": "shipping",
                                "description": "Phí vận chuyển",
                                "amount": 10.0,
                                "currency": "USD",
                            }
                        ],
                        "warranty_months": 12,
                        "lead_time_days": 7,
                    }
                ],
            },
        ),
        (
            "Test Case 2: Nhiều nhà cung cấp với nhiều loại đơn vị (EUR, JPY, hộp, cái)",
            {
                "pr_data": {
                    "pr_number": "PR-2026-002",
                    "quantity": 500,
                    "target_uom": "cái",
                    "target_currency": "VND",
                },
                "raw_extractions": [
                    {
                        "extraction_id": "ext-002",
                        "source": {"filename": "quote_supplier_b.pdf", "page_number": 1},
                        "supplier_id": "NCC Bảo Minh",
                        "item_name": "Bu lông M8",
                        "unit_price": 2.0,  # 2 EUR / hộp
                        "quantity": 50.0,  # 50 hộp (1 hộp = 10 cái)
                        "unit": "hộp",
                        "currency": "EUR",  # 1 EUR = 27,500 VND
                        "vat_rate": 0.08,
                        "vat_included": True,
                    },
                    {
                        "extraction_id": "ext-003",
                        "source": {"filename": "quote_supplier_c.pdf", "page_number": 1},
                        "supplier_id": "NCC Cường Thịnh",
                        "item_name": "Bu lông M8",
                        "unit_price": 40.0,  # 40 JPY / cái
                        "quantity": 500.0,
                        "unit": "cái",
                        "currency": "JPY",  # 1 JPY = 170 VND
                        "vat_rate": 0.1,
                        "vat_included": False,
                    },
                ],
            },
        ),
        (
            "Test Case 3: Đơn vị tính hoặc Tiền tệ lạ (cần đánh dấu manual conversion)",
            {
                "pr_data": {
                    "pr_number": "PR-2026-003",
                    "quantity": 100,
                    "target_uom": "cái",
                    "target_currency": "VND",
                },
                "raw_extractions": [
                    {
                        "extraction_id": "ext-004",
                        "source": {"filename": "quote_supplier_d.pdf", "page_number": 1},
                        "supplier_id": "NCC Delta Tech",
                        "item_name": "Vật tư đặc thù",
                        "unit_price": 500.0,
                        "quantity": 2.0,
                        "unit": "pallet_custom",  # ĐVT không có trong bảng quy đổi
                        "currency": "SGD",  # Tiền tệ không có trong bảng FX
                        "vat_rate": 0.1,
                    }
                ],
            },
        ),
    ]


def run_test(case_name: str, state: ProcurementAgentState) -> None:
    logger.info("\n" + "=" * 80)
    logger.info(f"[*] {case_name}")
    logger.info("=" * 80)

    pr_data = state.get("pr_data", {})
    logger.info(f"[PR Target] UOM='{pr_data.get('target_uom')}', Currency='{pr_data.get('target_currency')}'")

    raw_items = state.get("raw_extractions", [])
    logger.info(f"[Input] {len(raw_items)} raw extraction(s)")
    for r in raw_items:
        logger.info(
            f"   - [{r.get('supplier_id')}] {r.get('item_name')}: {r.get('quantity')} {r.get('unit')} @ {r.get('unit_price')} {r.get('currency')}"
        )

    # Chạy trực tiếp node normalize
    result = normalize(state)
    normalized_quotes = result.get("normalized_quotes", [])

    logger.info(f"\n[Output] {len(normalized_quotes)} supplier normalized quote(s):")
    for quote in normalized_quotes:
        logger.info(f"\n[Supplier] {quote.get('supplier_id')}")
        logger.info(f"   - has_manual_conversion: {quote.get('has_manual_conversion')}")
        for item in quote.get("items", []):
            logger.info(f"   - Item: {item.get('item_name')}")
            logger.info(
                f"      + Raw        : {item.get('quantity')} {item.get('unit')} @ {item.get('unit_price')} {item.get('currency')}"
            )
            norm_price = item.get("normalized_unit_price")
            norm_price_str = f"{norm_price:,.2f}" if isinstance(norm_price, (int, float)) else str(norm_price)
            logger.info(
                f"      + Normalized : {item.get('normalized_quantity')} {item.get('normalized_uom')} @ {norm_price_str} {item.get('normalized_currency')}"
            )
            if item.get("conversion_note"):
                logger.info(f"      + Note       : {item.get('conversion_note')}")
            if item.get("requires_manual_conversion"):
                logger.info("      [!] WARNING  : Cần chuyển đổi thủ công do ĐVT/Tiền tệ chưa có tỷ lệ quy đổi!")

            surcharges = item.get("surcharges", [])
            if surcharges:
                logger.info("      + Surcharges :")
                for s in surcharges:
                    norm_sc = s.get("normalized_amount")
                    norm_sc_str = f"{norm_sc:,.2f}" if isinstance(norm_sc, (int, float)) else str(norm_sc)
                    logger.info(
                        f"        * {s.get('description')}: {s.get('amount')} {s.get('currency')} -> {norm_sc_str} {s.get('normalized_currency')}"
                    )


def main():
    parser = argparse.ArgumentParser(description="Test tay cho Node normalize")
    parser.add_argument("--custom", type=str, help="Đường dẫn file JSON state tùy chỉnh")
    args = parser.parse_args()

    if args.custom:
        custom_file = Path(args.custom)
        if not custom_file.is_file():
            logger.error("File không tồn tại: %s", custom_file)
            sys.exit(1)
        with open(custom_file, encoding="utf-8") as f:
            custom_state = json.load(f)
        run_test(f"Custom Input từ {args.custom}", custom_state)
    else:
        sample_cases = build_sample_cases()
        for case_name, state in sample_cases:
            run_test(case_name, state)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
