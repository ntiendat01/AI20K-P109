import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Bật tracking LangSmith
os.environ["LANGCHAIN_TRACING_V2"] = "true"

from langgraph.types import Command  # noqa: E402

import src.services.llm as llm_service  # noqa: E402
from src.agents.graph import agent  # noqa: E402
from src.core.config import get_settings  # noqa: E402
from src.services.quotation.ai_extraction import GroqAPIExtractionClient  # noqa: E402

logger = logging.getLogger(__name__)

# Thư mục lưu output từng bước
OUTPUT_DIR = Path("output_steps")


# ==============================================================================
# HÀM VÀ CLASS ĐẾM / THEO DÕI TOKEN (TOKEN TRACKER)
# ==============================================================================


def count_tokens(text: str, model_name: str = "cl100k_base") -> int:
    """Đếm số lượng token của một chuỗi text bằng tiktoken (hoặc ước tính fallback)."""
    if not text:
        return 0
    try:
        import tiktoken

        try:
            encoding = tiktoken.encoding_for_model(model_name)
        except Exception:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        # Fallback ước tính: trung bình ~4 ký tự / 1 token tiếng Anh, ~1.5 - 2 token / từ tiếng Việt
        return max(1, int(len(text) / 3.5))


@dataclass
class LLMCallRecord:
    stage: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    source: str = "api_reported"  # 'api_reported' hoặc 'tiktoken_counted'
    notes: str = ""


class TokenUsageTracker:
    """Bộ ghi nhận và tổng hợp token tiêu thụ của toàn bộ pipeline."""

    def __init__(self):
        self.records: list[LLMCallRecord] = []

    def record(
        self,
        stage: str,
        model: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        prompt_text: str = "",
        completion_text: str = "",
        notes: str = "",
    ):
        source = "api_reported"
        in_tok = input_tokens
        out_tok = output_tokens

        # Nếu API không trả về token usage thì dùng tiktoken để đếm
        if in_tok is None:
            in_tok = count_tokens(prompt_text, model)
            source = "tiktoken_counted"
        if out_tok is None:
            out_tok = count_tokens(completion_text, model)
            source = "tiktoken_counted"

        total_tok = in_tok + out_tok
        rec = LLMCallRecord(
            stage=stage,
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=total_tok,
            source=source,
            notes=notes,
        )
        self.records.append(rec)
        return rec

    @property
    def total_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.records)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.records)

    @property
    def total_tokens(self) -> int:
        return sum(r.total_tokens for r in self.records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "total_calls": len(self.records),
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_tokens": self.total_tokens,
            },
            "calls": [asdict(r) for r in self.records],
        }

    def log_summary(self):
        logger.info("\n" + "=" * 80)
        logger.info("📊 BẢNG TỔNG HỢP TOKEN ĐẦU VÀO / ĐẦU RA CỦA LLM")
        logger.info("=" * 80)
        logger.info(
            f"{'STT':<4} | {'Giai đoạn (Stage)':<30} | {'Model':<20} | {'Input':<8} | {'Output':<8} | {'Total':<8}"
        )
        logger.info("-" * 80)
        for idx, r in enumerate(self.records, 1):
            logger.info(
                f"{idx:<4} | {r.stage:<30} | {r.model:<20} | {r.input_tokens:<8} | {r.output_tokens:<8} | {r.total_tokens:<8}"
            )
        logger.info("-" * 80)
        logger.info(f"👉 TỔNG CỘNG: {len(self.records)} lần gọi LLM")
        logger.info(f"   • Tổng Input Tokens  : {self.total_input_tokens:,}")
        logger.info(f"   • Tổng Output Tokens : {self.total_output_tokens:,}")
        logger.info(f"   • TỔNG TOKENS TIÊU THỤ: {self.total_tokens:,}")
        logger.info("=" * 80)


# Khởi tạo singleton tracker cho phiên chạy
tracker = TokenUsageTracker()


# ==============================================================================
# WRAPPER THEO DÕI TOKEN TỰ ĐỘNG CHO CÁC SERVICE LLM
# ==============================================================================


class TrackedGroqExtractionClient(GroqAPIExtractionClient):
    """Kế thừa Groq client để tự động bắt và ghi nhận số token trả về từ response."""

    def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, object]]:
        import httpx

        settings = get_settings()
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")

        base_url = settings.groq_base_url.rstrip("/")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.groq_api_key}",
        }
        from src.services.quotation.ai_extraction import _fit_context_window

        ocr_text_fitted = _fit_context_window(
            ocr_text, settings.extraction_prompt, document_path, max_input_tokens=4500
        )

        prompt_content = json.dumps({"document": document_path, "ocr_result": ocr_text_fitted}, ensure_ascii=False)
        payload = {
            "model": settings.groq_model_name,
            "temperature": 0,
            "max_tokens": 3500,
            "messages": [
                {"role": "system", "content": settings.extraction_prompt},
                {"role": "user", "content": prompt_content},
            ],
        }

        response = httpx.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=60.0)
        response.raise_for_status()
        resp_json = response.json()

        # Đọc usage từ response hoặc đếm bằng tiktoken
        usage = resp_json.get("usage", {})
        in_tok = usage.get("prompt_tokens")
        out_tok = usage.get("completion_tokens")
        completion_content = resp_json.get("choices", [{}])[0].get("message", {}).get("content", "")

        tracker.record(
            stage=f"Extraction ({Path(document_path).name[:25]})",
            model=settings.groq_model_name,
            input_tokens=in_tok,
            output_tokens=out_tok,
            prompt_text=settings.extraction_prompt + prompt_content,
            completion_text=completion_content,
            notes=f"Document: {document_path}",
        )

        from src.services.quotation.ai_extraction import _parse_qwen_response

        return _parse_qwen_response(resp_json)


# Bọc LLM decision để đếm token
original_get_llm = llm_service.get_llm


def tracked_get_llm():
    llm = original_get_llm()
    original_invoke = llm.invoke

    def wrapped_invoke(*args, **kwargs):
        resp = original_invoke(*args, **kwargs)
        # Lấy token usage từ LangChain message metadata nếu có
        in_tok = None
        out_tok = None
        if hasattr(resp, "usage_metadata") and isinstance(resp.usage_metadata, dict):
            in_tok = resp.usage_metadata.get("input_tokens")
            out_tok = resp.usage_metadata.get("output_tokens")
        elif hasattr(resp, "response_metadata") and isinstance(resp.response_metadata, dict):
            usage = resp.response_metadata.get("token_usage", {})
            in_tok = usage.get("prompt_tokens")
            out_tok = usage.get("completion_tokens")

        prompt_str = str(args[0]) if args else ""
        content_str = getattr(resp, "content", "")

        settings = get_settings()
        model_name = getattr(llm, "model_name", getattr(llm, "model", settings.groq_model_name))
        tracker.record(
            stage="Decision LLM (Ranking)",
            model=str(model_name),
            input_tokens=in_tok,
            output_tokens=out_tok,
            prompt_text=prompt_str,
            completion_text=str(content_str),
            notes="Ranking & rationale generation",
        )
        return resp

    llm.invoke = wrapped_invoke
    return llm


llm_service.get_llm = tracked_get_llm


def save_step_output(step_number: int, node_name: str, node_output: dict, cumulative_state: dict | None = None) -> Path:
    """Lưu dữ liệu output của từng node vào một file JSON riêng biệt."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    file_path = OUTPUT_DIR / f"{step_number:02d}_{node_name}.json"

    payload = {
        "step": step_number,
        "node_name": node_name,
        "node_output": node_output,
    }
    if cumulative_state is not None:
        payload["cumulative_state"] = cumulative_state

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    return file_path


@patch("src.agents.nodes.extract_documents.GeminiAPIExtractionClient", new=TrackedGroqExtractionClient)
def run_pipeline():
    pdf_paths = [r"V:\02_VietNhat_Quotation.pdf", r"V:\01_HoaPhat_Quotation.pdf"]
    logger.info("🚀 Khởi chạy Full Pipeline tự động với 2 tài liệu và MOCK LLM")
    logger.info(f"📁 Thư mục lưu output từng bước: {OUTPUT_DIR.resolve()}\n")

    # Tạo/dọn thư mục output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Tạo initial state
    initial_state = {
        "documents": pdf_paths,
        "pr_data": {
            "pr_number": "PR-TEST-AUTO",
            "quantity": 2000.0,
            "target_uom": "cái",
            "target_currency": "VND",
        },
        "top_n": 3,
    }

    # Lưu initial state
    save_step_output(0, "initial_state", initial_state)
    logger.info(f"💾 [Bước 00] Đã lưu Initial State vào: {OUTPUT_DIR / '00_initial_state.json'}")

    config = {"configurable": {"thread_id": "auto_test_thread"}}
    step_counter = 1

    try:
        # Bước 1: Khởi động Graph bằng chế độ stream để xem từng node
        logger.info("\n>> Bắt đầu chạy Graph (Stream từng Node)...")
        current_input = initial_state

        while True:
            # Stream từng bước để xem node output trước khi chuyển
            for step_output in agent.stream(current_input, config=config, stream_mode="updates"):
                for node_name, node_output in step_output.items():
                    logger.info(f"\n[NODE COMPLETED] : {node_name}")

                    # Lấy snapshot state hiện tại
                    state_snapshot = agent.get_state(config)
                    current_values = state_snapshot.values if state_snapshot else None

                    # Lưu output của node ra file riêng
                    saved_path = save_step_output(
                        step_number=step_counter,
                        node_name=node_name,
                        node_output=node_output if isinstance(node_output, dict) else {"raw": node_output},
                        cumulative_state=current_values,
                    )
                    logger.info(f"   💾 Đã lưu output node ra file: {saved_path}")
                    step_counter += 1

                    if not isinstance(node_output, dict):
                        logger.info(f"   => Dữ liệu trả về (không phải dạng chuẩn): {node_output}")
                        continue

                    logger.info(f"   => Các trường state được cập nhật: {list(node_output.keys())}")

                    if "raw_extractions" in node_output:
                        logger.info(f"      - Đã trích xuất {len(node_output['raw_extractions'])} dòng báo giá thô.")
                    if "normalized_quotes" in node_output:
                        logger.info(
                            f"      - Đã chuẩn hóa {len(node_output['normalized_quotes'])} báo giá nhà cung cấp."
                        )
                    if "tco_results" in node_output:
                        logger.info(
                            f"      - Tính xong TCO cho: {[t.get('supplier_id') for t in node_output['tco_results']]}"
                        )
                    if "recommendation" in node_output and isinstance(node_output["recommendation"], dict):
                        ranked = node_output["recommendation"].get("ranked", [])
                        logger.info(f"      - Xếp hạng bởi AI: {[r.get('supplier_id', '') for r in ranked]}")

            # Kiểm tra trạng thái hiện tại (có bị interrupt hay đã end)
            state_snapshot = agent.get_state(config)
            next_node = state_snapshot.next

            if not next_node:
                logger.info("\n>> Graph đã chạy đến END! Hoàn tất.")
                result = state_snapshot.values
                break

            logger.info("\n⏳ GRAPH TẠM DỪNG (Interrupt) CHỜ USER.")
            logger.info(f"   => Sẽ chuyển qua node tiếp theo: {next_node[0]}")
            logger.info(f"   => Một phần Output đang có trong State trước khi vào {next_node[0]}:")
            if next_node[0] == "human_review_extraction":
                logger.info(
                    f"      + Số raw extractions hiện tại: {len(state_snapshot.values.get('raw_extractions', []))}"
                )
            elif next_node[0] == "human_review_recommendation":
                rec = state_snapshot.values.get("recommendation", {})
                if rec and "ranked" in rec and len(rec["ranked"]) > 0:
                    logger.info(f"      + Top 1 Recommend hiện tại: {rec['ranked'][0].get('supplier_id')}")

            # Giả lập thao tác của User (Auto-Approve mọi thứ)
            if next_node[0] == "human_review_extraction":
                logger.info("   => [User Action] Xác nhận kết quả trích xuất OCR hợp lệ.")
                feedback = {"response": "Looks good, proceed."}
            elif next_node[0] == "human_review_recommendation":
                logger.info("   => [User Action] Đồng ý với bảng xếp hạng của AI.")
                feedback = {"decision": "approved", "response": "OK"}
            else:
                feedback = {"response": "Auto continue"}

            logger.info("   => Tiếp tục (Resume) chạy Graph...")
            current_input = Command(resume=feedback)

        logger.info("\n🎉 === TRẠNG THÁI CUỐI CÙNG ===")

        # 1. Báo giá thô (Raw Extractions)
        raw_ext = result.get("raw_extractions", [])
        logger.info(f"\n📦 1. BÁO GIÁ THÔ (RAW EXTRACTIONS) - {len(raw_ext)} mục:")
        for i, ext in enumerate(raw_ext, 1):
            supplier = ext.get("supplier_id", "Unknown")
            item = ext.get("item_name", "Unknown")
            qty = ext.get("quantity")
            price = ext.get("unit_price")
            logger.info(f"   {i}. [{supplier}] {item} | SL: {qty} | Giá: {price}")

        # 2. Báo giá chuẩn hóa (Normalized Quotes)
        norm_quotes = result.get("normalized_quotes", [])
        logger.info(f"\n🔄 2. BÁO GIÁ CHUẨN HÓA (NORMALIZED QUOTES) - {len(norm_quotes)} nhà cung cấp:")
        for nq in norm_quotes:
            supplier = nq.get("supplier_id", "Unknown")
            items = nq.get("items", [])
            logger.info(f"   - Nhà cung cấp: {supplier} ({len(items)} items)")
            for it in items:
                logger.info(
                    f"     + {it.get('item_name')} | Đã chuẩn hóa giá: {it.get('normalized_unit_price')} | Cần tự quy đổi: {it.get('requires_manual_conversion')}"
                )

        # 3. Tính toán TCO (TCO Results)
        tco_results = result.get("tco_results", [])
        logger.info(f"\n💰 3. TÍNH TOÁN TCO (TCO RESULTS) - {len(tco_results)} nhà cung cấp:")
        for tco in tco_results:
            supplier = tco.get("supplier_id", "Unknown")
            total = tco.get("total_tco", "N/A")
            status = tco.get("status", "Unknown")
            missing = tco.get("missing_fields", [])
            logger.info(f"   - [{supplier}] Total TCO: {total} | Status: {status}")
            if missing:
                logger.info(f"     -> Thiếu dữ liệu: {missing}")

        # 4. Rủi ro (Risk Flags)
        risks = result.get("risk_flags", [])
        logger.info(f"\n⚠️ 4. CẢNH BÁO RỦI RO (RISK FLAGS) - {len(risks)} cảnh báo:")
        for risk in risks:
            sev = risk.get("severity", "info").upper()
            supplier = risk.get("supplier_id", "Unknown")
            msg = risk.get("message", "")
            logger.info(f"   - [{sev}] {supplier}: {msg}")

        # 5. Khuyến nghị (Recommendation)
        recommendation = result.get("recommendation", {})
        ranked = recommendation.get("ranked", [])
        logger.info(f"\n🏆 5. ĐỀ XUẤT XẾP HẠNG (RECOMMENDATION) - {len(ranked)} nhà cung cấp:")
        for r in ranked:
            sup = r.get("supplier_id") or r.get("supplier")
            logger.info(f"   - Hạng {r.get('rank')}: {sup}")
            logger.info(f"     Lý do: {r.get('rationale')}")
            logger.info(f"     Bằng chứng: {len(r.get('evidence', []))} citations.")

        # Lưu kết quả tổng hợp
        output_file = PROJECT_ROOT / "artifacts" / "manual" / "full_pipeline_output.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"\n=> Chi tiết toàn bộ State đã được lưu vào: {output_file}")

        final_step_file = OUTPUT_DIR / f"{step_counter:02d}_final_state.json"
        with open(final_step_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"=> Snapshot State cuối cùng đã được lưu vào: {final_step_file}")

        # In và lưu thống kê token tiêu thụ
        tracker.log_summary()
        token_summary_file = OUTPUT_DIR / "token_usage_summary.json"
        with open(token_summary_file, "w", encoding="utf-8") as f:
            json.dump(tracker.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Thống kê chi tiết token đã lưu vào: {token_summary_file}")

    except Exception:
        logger.exception("Lỗi khi chạy pipeline")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_pipeline()
