import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout.reconfigure(encoding="utf-8")

from src.agents.nodes.extract_documents import extract_documents  # noqa: E402

logger = logging.getLogger(__name__)


def main():
    if len(sys.argv) < 2:
        logger.info("Sử dụng: python scripts/manual/run_ocr.py <đường_dẫn_tới_file_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not os.path.exists(pdf_path):
        logger.error("Không tìm thấy file %s", pdf_path)
        sys.exit(1)

    logger.info(f"Đang phân tích file: {pdf_path}...")
    logger.info("Vui lòng đợi (quá trình OCR và gọi Qwen LLM có thể mất vài chục giây)...")

    # Tạo state giả lập để truyền vào node
    mock_state = {"documents": [pdf_path], "pr_data": {}}

    try:
        result = extract_documents(mock_state)
        logger.info("\n=== KẾT QUẢ TRÍCH XUẤT ===")
        logger.info(json.dumps(result["raw_extractions"], indent=2, ensure_ascii=False))
    except Exception:
        logger.exception("Lỗi trong quá trình xử lý OCR")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
