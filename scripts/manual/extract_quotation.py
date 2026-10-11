"""Script chạy test tay cho LLM Extractor (Gemini / Groq / Qwen).

Hỗ trợ kiểm tra:
1. Khả năng trích xuất từ OCR text mẫu sang JSON có cấu trúc đầy đủ.
2. Kiểm tra độ chính xác của các trường: Đơn giá, ĐVT, Tiền tệ, VAT, Phụ phí, Lead time, Bảo hành.
3. Điểm tin cậy (confidence_score & field_confidence).

Cách chạy:
    .venv\\Scripts\\python scripts/manual/extract_quotation.py --extractor gemini
    .venv\\Scripts\\python scripts/manual/extract_quotation.py --extractor groq
    .venv\\Scripts\\python scripts/manual/extract_quotation.py --extractor qwen
    .venv\\Scripts\\python scripts/manual/extract_quotation.py --text-file path/to/ocr_text.txt
"""

from __future__ import annotations

import argparse
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

from src.services.quotation.ai_extraction import (  # noqa: E402
    ExtractionClient,
    GeminiAPIExtractionClient,
    GroqAPIExtractionClient,
    QwenAPIExtractionClient,
)

logger = logging.getLogger(__name__)

SAMPLE_OCR_TEXT = """
CÔNG TY TNHH THIẾT BỊ VÀ CÔNG NGHỆ AN PHÁT
Địa chỉ: 123 Đường Giải Phóng, Quận Hai Bà Trưng, Hà Nội
BÁO GIÁ THIẾT BỊ & VẬT TƯ
Số: BG-2026/03-AP
Ngày: 15/03/2026

Kính gửi: PHÒNG MUA HÀNG - CÔNG TY ABC

Chúng tôi xin trân trọng gửi báo giá chi tiết các mặt hàng như sau:

STT | Tên hàng hóa / Quy cách               | ĐVT   | Số lượng | Đơn giá (VNĐ) | Thành tiền (VNĐ)
 1  | Bu lông lục giác chìm M8x30 Inox 304   | thùng |    5     |   1,250,000   |    6,250,000
    | (Quy cách đóng gói: 200 chiếc/thùng)  |       |          |               |
 2  | Đai ốc tự khóa M8 Inox 304            | hộp   |   20     |     180,000   |    3,600,000
    | (Quy cách đóng gói: 50 chiếc/hộp)     |       |          |               |

Tổng cộng tiền hàng trước thuế: 9,850,000 VNĐ
Thuế VAT (8%): 788,000 VNĐ
Phí bốc xếp & vận chuyển tận nơi: 250,000 VNĐ (chưa gồm VAT)
Tổng thanh toán: 10,888,000 VNĐ

ĐIỀU KHOẢN THƯƠNG MẠI:
- Đơn giá trên chưa bao gồm thuế GTGT 8%.
- Thời gian giao hàng: Giao trong vòng 3 - 5 ngày làm việc kể từ ngày nhận được PO.
- Thời hạn bảo hành: Bảo hành tiêu chuẩn nhà sản xuất 12 tháng.
- Thanh toán: Chuyển khoản trong vòng 30 ngày sau khi nhận đủ hàng và hóa đơn hợp lệ.
"""


def get_client(extractor_name: str) -> ExtractionClient:
    name = extractor_name.lower().strip()
    if name == "gemini":
        return GeminiAPIExtractionClient()
    elif name == "groq":
        return GroqAPIExtractionClient()
    elif name == "qwen":
        return QwenAPIExtractionClient()
    else:
        raise ValueError(f"Extractor không hợp lệ: '{extractor_name}'. Chọn: gemini, groq, qwen")


def test_extractor(extractor_name: str, ocr_text: str, doc_name: str = "sample_quote.pdf") -> None:
    logger.info("\n" + "=" * 80)
    logger.info(f"[*] BẮT ĐẦU TEST LLM EXTRACTOR: [{extractor_name.upper()}]")
    logger.info(f"[*] Tài liệu giả định: {doc_name}")
    logger.info("=" * 80)

    logger.info("\n--- [1] NỘI DUNG OCR ĐẦU VÀO ---")
    logger.info(ocr_text.strip()[:600] + "\n...[nội dung tiếp theo]..." if len(ocr_text) > 600 else ocr_text.strip())
    logger.info("-" * 80)

    client = get_client(extractor_name)
    logger.info(f"\n[+] Đang gửi yêu cầu trích xuất tới {extractor_name.upper()} API...")

    try:
        items = client.extract_items(ocr_text, doc_name)
    except Exception:
        logger.exception("Lỗi trích xuất với extractor=%s", extractor_name)
        return

    logger.info(f"\n[+] Trích xuất thành công: {len(items)} dòng mặt hàng (items)")
    logger.info("\n--- [2] KẾT QUẢ CẤU TRÚC JSON ---")

    for idx, item in enumerate(items, 1):
        logger.info(f"\n📦 Item #{idx}:")
        logger.info(f"   • Nhà cung cấp (supplier)      : {item.get('supplier') or item.get('supplier_id')}")
        logger.info(f"   • Tên mặt hàng (item_name)     : {item.get('item_name')}")
        logger.info(f"   • Số lượng & ĐVT               : {item.get('quantity')} {item.get('unit')}")
        logger.info(f"   • Đơn giá & Tiền tệ            : {item.get('unit_price')} {item.get('currency')}")
        logger.info(
            f"   • Thuế VAT                     : rate={item.get('vat_rate')}, included={item.get('vat_included')}"
        )
        logger.info(f"   • Phụ phí (surcharges)         : {item.get('surcharges')}")
        logger.info(f"   • Thời hạn bảo hành (warranty) : {item.get('warranty_months')} tháng")
        logger.info(
            f"   • Thời gian giao (lead time)   : {item.get('lead_time_days')} ngày (min={item.get('lead_time_min')}, max={item.get('lead_time_max')}, unit={item.get('lead_time_unit')})"
        )
        logger.info(f"   • Điểm tin cậy (confidence)    : {item.get('confidence_score')}")
        logger.info(f"   • Chi tiết tin cậy từng trường : {item.get('field_confidence')}")

    logger.info("\n" + "=" * 80)
    logger.info("[*] TEST HOÀN TẤT")
    logger.info("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Test tay LLM Extractor cho Báo giá")
    parser.add_argument(
        "--extractor",
        choices=["gemini", "groq", "qwen"],
        default="gemini",
        help="Chọn LLM backend: gemini (mặc định), groq, qwen",
    )
    parser.add_argument(
        "--text-file",
        type=str,
        help="Đường dẫn file text chứa nội dung OCR tùy chỉnh",
    )
    args = parser.parse_args()

    ocr_text = SAMPLE_OCR_TEXT
    doc_name = "sample_quote_an_phat.pdf"

    if args.text_file:
        text_path = Path(args.text_file)
        if not text_path.is_file():
            logger.error("File không tồn tại: %s", text_path)
            sys.exit(1)
        ocr_text = text_path.read_text(encoding="utf-8")
        doc_name = text_path.name

    test_extractor(args.extractor, ocr_text, doc_name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
