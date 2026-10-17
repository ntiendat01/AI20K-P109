"""
Batch Quotation Extraction Script
=================================
Chạy trích xuất hàng loạt file PDF trong thư mục:
1. Quét toàn bộ file PDF trong thư mục được chỉ định.
2. Thực hiện trích xuất (page-aware PDF text/OCR + LLM Extraction Draft).
3. Đo thời gian phản hồi (Response Time / Latency).
4. Lưu kết quả trích xuất ra từng file JSON độc lập (<stem>_ocr.json).
5. Áp dụng delay giữa các request để tuân thủ rate limit.
6. Hiển thị báo cáo tiến độ chi tiết và bảng tổng kết thời gian xử lý.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Thêm thư mục gốc vào PYTHONPATH
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

# Đảm bảo hiển thị Unicode trên Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("batch_extract")


def extract_single_pdf(pdf_path: Path) -> dict[str, Any]:
    """
    Thực hiện trích xuất dữ liệu từ PDF qua pipeline hệ thống:
    1. Đọc văn bản theo từng trang qua OCR service, ưu tiên lớp text và OCR các trang cần thiết.
    2. Gọi LLM trích xuất cấu trúc báo giá.
    3. Trả về cấu trúc JSON chuẩn gồm raw_extractions và validated_extractions.
    """
    from src.agents.nodes.extract_documents import extract_documents
    from src.agents.nodes.validate_extraction import validate_extraction
    from src.application.quotation.intake import ConfiguredExtraction
    from src.infrastructure.documents.pdf_extractor import PDFTextExtractor

    ocr_client = PDFTextExtractor()
    extraction_client = ConfiguredExtraction()

    initial_state = {"documents": [str(pdf_path)]}
    extracted_state = extract_documents(
        initial_state,
        ocr_client=ocr_client,
        extraction_client=extraction_client,
    )
    validated_state = validate_extraction(extracted_state)

    return {
        "case_id": pdf_path.stem,
        "documents": [str(pdf_path)],
        "raw_extractions": extracted_state.get("raw_extractions", []),
        "review_mode": validated_state.get("review_mode", "mandatory"),
        "validated_extractions": [
            v.model_dump(mode="json") if hasattr(v, "model_dump") else v
            for v in validated_state.get("validated_extractions", [])
        ],
    }


def run_batch_extraction(
    docs_dir: Path,
    output_dir: Path,
    delay_seconds: float = 16.0,
    max_files: int | None = None,
    file_suffix: str = "_ocr.json",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(docs_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"❌ Không tìm thấy file PDF nào trong thư mục: {docs_dir}")
        return

    if max_files:
        pdf_files = pdf_files[:max_files]

    total_files = len(pdf_files)
    print("=" * 80)
    print(f"🚀 BẮT ĐẦU CHẠY TRÍCH XUẤT HÀNG LOẠT ({total_files} files)")
    print(f"📁 Thư mục PDF nguồn:  {docs_dir}")
    print(f"📁 Thư mục lưu JSON:   {output_dir}")
    print(f"⏱️ Delay mỗi request:  {delay_seconds}s (tránh chạm rate limit)")
    print("=" * 80)

    summary_records: list[dict[str, Any]] = []

    for index, pdf_path in enumerate(pdf_files, 1):
        print(f"\n[{index}/{total_files}] 📄 Đang trích xuất: {pdf_path.name} ...")
        start_time = time.perf_counter()
        error_msg = None
        extracted_data = None
        out_file = output_dir / f"{pdf_path.stem}_ocr.json"

        try:
            # 1. Chạy bước extract
            extracted_data = extract_single_pdf(pdf_path)
            latency_seconds = time.perf_counter() - start_time

            # 2. Ghi ra file JSON kết quả
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(extracted_data, f, ensure_ascii=False, indent=2)

            items_count = 0
            if extracted_data.get("raw_extractions"):
                items_count = len(extracted_data["raw_extractions"][0].get("items", []))

            print(f"    ✓ Thành công trong {latency_seconds:.2f}s | Trích xuất được {items_count} mặt hàng")
            print(f"    💾 Đã lưu JSON: {out_file.name}")

        except Exception as e:
            latency_seconds = time.perf_counter() - start_time
            error_msg = str(e)
            print(f"    ❌ Lỗi: {error_msg}")

        summary_records.append({
            "stt": index,
            "file_name": pdf_path.name,
            "output_json": out_file.name if not error_msg else None,
            "latency_seconds": round(latency_seconds, 2),
            "status": "SUCCESS" if not error_msg else "ERROR",
            "error": error_msg,
        })

        # Áp dụng delay nếu còn file tiếp theo
        if index < total_files and delay_seconds > 0:
            print(f"    ⏳ Chờ {delay_seconds:.1f}s trước khi gọi file tiếp theo...")
            time.sleep(delay_seconds)

    # 3. Xuất file tổng kết thống kê thời gian
    summary_path = output_dir / "batch_extraction_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_records, f, ensure_ascii=False, indent=2)

    # 4. In bảng báo cáo tổng kết ra console
    print("\n" + "=" * 80)
    print("📊 BÁO CÁO TỔNG KẾT TIẾN ĐỘ TRÍCH XUẤT")
    print("=" * 80)
    print(f"{'STT':<4} | {'Tên File PDF':<38} | {'Thời gian':<10} | {'Trạng thái'}")
    print("-" * 80)

    successful = [r for r in summary_records if r["status"] == "SUCCESS"]
    latencies = [r["latency_seconds"] for r in successful]

    for r in summary_records:
        name_str = (r["file_name"][:35] + "...") if len(r["file_name"]) > 38 else r["file_name"]
        time_str = f"{r['latency_seconds']:.2f}s"
        status_str = "✅ SUCCESS" if r["status"] == "SUCCESS" else "❌ ERROR"
        print(f"{r['stt']:<4} | {name_str:<38} | {time_str:<10} | {status_str}")

    print("-" * 80)
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    min_latency = min(latencies) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0

    print(f"Tổng số file xử lý:   {len(summary_records)}")
    print(f"Trích xuất thành công: {len(successful)} / {len(summary_records)}")
    print(f"Thời gian TB (Latency): {avg_latency:.2f}s (Nhanh nhất: {min_latency:.2f}s, Lâu nhất: {max_latency:.2f}s)")
    print(f"📁 Toàn bộ file JSON lưu tại: {output_dir}")
    print(f"📄 Báo cáo tổng hợp:         {summary_path}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Trích xuất hàng loạt file PDF báo giá ra file JSON")
    parser.add_argument(
        "--docs-dir",
        type=str,
        default="V:/eval/golden_dataset/documents",
        help="Thư mục chứa các file PDF cần trích xuất (mặc định: V:/eval/golden_dataset/documents)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=r"V:\eval\golden_dataset\ground_truth",
        help="Thư mục lưu trữ các file JSON kết quả trích xuất",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=16.0,
        help="Thời gian nghỉ (giây) giữa mỗi request để tránh rate-limit (mặc định: 16s)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Giới hạn số lượng file chạy thử (ví dụ: --max-files 3)",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_ocr.json",
        help="Hậu tố tên file JSON kết quả (mặc định: _ocr.json)",
    )

    args = parser.parse_args()

    run_batch_extraction(
        docs_dir=Path(args.docs_dir),
        output_dir=Path(args.output_dir),
        delay_seconds=args.delay,
        max_files=args.max_files,
        file_suffix=args.suffix,
    )


if __name__ == "__main__":
    main()
