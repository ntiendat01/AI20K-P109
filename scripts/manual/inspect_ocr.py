import json
import logging
import sys
from importlib import import_module

sys.stdout.reconfigure(encoding="utf-8")

logger = logging.getLogger(__name__)


def extract_page_texts(page_data):
    """Return recognized text lines from PaddleOCR v3 or legacy output."""
    if isinstance(page_data, dict):
        rec_texts = page_data.get("rec_texts", [])
        return [text for text in rec_texts if isinstance(text, str)]

    if isinstance(page_data, list):
        texts = []
        for line in page_data:
            if not isinstance(line, (list, tuple)) or len(line) != 2:
                continue
            recognition = line[1]
            if isinstance(recognition, (list, tuple)) and recognition:
                text = recognition[0]
                if isinstance(text, str):
                    texts.append(text)
        return texts

    return []


def test_ocr(document_path):
    logger.info("Loading PaddleOCR...")
    module = import_module("paddleocr")
    paddle_ocr_class = getattr(module, "PaddleOCR")

    client = paddle_ocr_class(lang="vi", ocr_version="PP-OCRv3", enable_mkldnn=False)

    logger.info(f"\nRunning OCR on {document_path}...")
    result = client.ocr(document_path)

    logger.info("\n=== RAW OCR RESULT (First 1000 characters) ===")
    res_str = str(result)
    logger.info(res_str[:1000] + ("..." if len(res_str) > 1000 else ""))

    extracted_pages = []
    if isinstance(result, list):
        if result and isinstance(result[0], dict):
            logger.info(f"\nKeys in result[0]: {list(result[0].keys())}")

        for page_data in result:
            page_texts = extract_page_texts(page_data)
            extracted_pages.append({"raw_text": "\n".join(page_texts)})

    payload = {"pages": extracted_pages}
    logger.info("\n=== PARSED TEXT SENT TO LLM ===")
    logger.info(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) > 1:
        test_ocr(sys.argv[1])
    else:
        logger.info("Vui lòng cung cấp đường dẫn file.")
