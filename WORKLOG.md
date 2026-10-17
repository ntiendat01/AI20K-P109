# Worklog — Team P-109 · Procurement Agent

> Ghi lại tất cả công việc đã làm theo ngày. Ai làm gì, kết quả gì.Đề tài: AI Agent Xử lý Đề nghị Mua sắm & So sánh Nhà cung cấp.

---

## 2026-09-19 → 2026-09-20 (Tuần 1 · Chọn đề tài)

| Member  | Task                                                                                                                      | Status | Output                                                                                                                                   | Time |
| ------- | ------------------------------------------------------------------------------------------------------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| Cả nhóm | Nghiên cứu, sàng lọc và chọn ra 3 đề tài tiềm năng                                                                        | ✅ Done | Danh sách 3 đề tài                                                                                                                       | -    |
| Cả nhóm | Tìm hiểu nghiệp vụ từng đề tài; đánh giá theo tính khả thi, giá trị thực tiễn, độ phù hợp LLM/Agent, khối lượng công việc | ✅ Done | Bảng so sánh tiêu chí                                                                                                                    | -    |
| Cả nhóm | Thống nhất chọn đề tài, xác định rõ bài toán                                                                              | ✅ Done | Chốt đề tài Procurement Agent: nhận PR, trích xuất báo giá, so sánh NCC, đề xuất kèm lý do; con người duyệt (HITL) ở các điểm quyết định | -    |

**Tổng kết ngày:** Chốt đề tài và phạm vi bài toán: Phòng Mua sắm đang so sánh báo giá thủ công, dễ sai sót, thiếu minh bạch; agent hỗ trợ nhưng không tự đặt hàng.

---

## 2026-09-21 → 2026-09-27 (Tuần 2 · Thiết kế giải pháp & nghiên cứu công nghệ)

| Member                 | Task                                                                                                                                                | Status | Output                                                                                                                                                                                                           | Time |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| Nguyễn Thu Trang       | Thiết kế kiến trúc: pipeline LangGraph 2 pha (Extraction → Analysis/Recommendation), tách Frontend – Backend – Agent – OCR, xác định 2 điểm HITL    | ✅ Done | `ARCHITECTURE.md`, `docs/architecture_diagram.md`, `docs/state-machine.md`                                                                                                                                       | -    |
| Nguyễn Mai Hoàng Thiện | Thiết kế mô hình dữ liệu và contract Pydantic: PR, báo giá, nhà cung cấp, TCO/so sánh/rủi ro, đề xuất, phê duyệt, PO, audit                         | ✅ Done | `src/domain/` (procurement, quotation, analysis, approval, purchase\_order)                                                                                                                                      | -    |
| Nguyễn Tiến Đạt        | Thiết kế kỹ thuật: API, phân quyền 2 vai trò (Nhân viên mua sắm / Quản lý duyệt), luồng xử lý tài liệu, ràng buộc về bảo mật, độ chính xác, chi phí | ✅ Done | `docs/specs/` (mvp, login\_and\_decentralization, create\_and\_manage\_PR, upload\_and\_extract\_quotes, data\_normalization, supplier\_comparison\_and\_recommendations, review\_and\_create\_PO, user-stories) | -    |
| Trần Mạnh Hùng         | Nghiên cứu công cụ: LangGraph, OCR/parser bảng cho báo giá PDF, lưu trữ evidence dạng vector, FastAPI/React/PostgreSQL, hạ tầng deploy              | ✅ Done | Chốt stack: FastAPI + LangGraph + OCR service riêng (RapidOCR/PaddleOCR) + pdfplumber/pypdf + PostgreSQL (pgvector) + React/Vite/TypeScript + Docker Compose                                                     | -    |
| Cả nhóm                | Chia nhỏ công việc cho giai đoạn phát triển                                                                                                         | ✅ Done | `docs/tasks/INDEX.md` (T-01 → T-17)                                                                                                                                                                              | -    |

**Tổng kết ngày:** Hoàn thành tài liệu thiết kế (kiến trúc, mô hình dữ liệu, thiết kế kỹ thuật), chốt tech stack và phân công. Nguyên tắc thiết kế đã chốt: số liệu tiền/TCO tính bằng code tất định (không để LLM làm toán), LLM chỉ tổng hợp và giải trình.

---

## 2026-09-28 → 2026-10-04 (Tuần 3 · Thành phần cốt lõi & MVP)

| Member                 | Task                                                                                                                                                                                                                                                             | Status | Output                                                                                                       | Time |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------ | ---- |
| Nguyễn Mai Hoàng Thiện | Xây dựng graph LangGraph: `extract_documents` → `validate_extraction` → `confidence_router` → `human_review_extraction` (HITL-1) → `normalize` → `decision_llm` → `evaluate` → `generate_evidence` → `human_review_recommendation` (HITL-2) → `process_feedback` | ✅ Done | `src/agents/graph.py`, `src/agents/state.py`, `src/agents/nodes/`                                            | -    |
| Nguyễn Thu Trang       | Xây dựng tool tất định: chuẩn hóa UOM/tiền tệ, `calculate_tco`, `compare_suppliers` (highlight ô lệch quá ngưỡng cấu hình), `analyze_risks` (thiếu lead time, giao trễ so với hạn PR, chi phí ẩn)                                                                | ✅ Done | `src/agents/tools/` + `tests/` (đáp án tính tay)                                                             | -    |
| Trần Mạnh Hùng         | Tích hợp LLM, thiết kế prompt và đầu ra có cấu trúc (JSON theo schema) cho trích xuất và `DecisionProposal`; provider chọn qua cấu hình (`llm_provider`: OpenAI, OpenRouter, Groq, Qwen)                                                                         | ✅ Done | `src/infrastructure/llm.py`, `src/core/config.py`, `src/infrastructure/quotation/ai_extraction.py`           | -    |
| Trần Mạnh Hùng         | Trích xuất báo giá: ưu tiên text layer PDF theo trang, trang thiếu text gọi OCR service; trả trường kèm `confidence_score`                                                                                                                                       | ✅ Done | `src/infrastructure/documents/`, `src/infrastructure/ocr/`, `ocr/ocr_service/`                               | -    |
| Nguyễn Mai Hoàng Thiện | Monitoring & tracing: cấu hình LangSmith tracing và logging có cấu trúc để truy vết từng bước chạy                                                                                                                                                               | ✅ Done | `src/core/logging.py`, cấu hình `langchain_*` trong `src/core/config.py`                                     | -    |
| Nguyễn Tiến Đạt        | Nghiên cứu nghiệp vụ Procure-to-Pay (PR → báo giá → đánh giá NCC → duyệt → PO), điều chỉnh logic so sánh/đề xuất theo tiêu chí giá/TCO, lead time, bảo hành, thanh toán                                                                                          | ✅ Done | Cập nhật `docs/specs/`, logic ở `src/domain/analysis/`                                                       | -    |
| Nguyễn Tiến Đạt        | MVP nghiệp vụ: đăng nhập 2 vai trò + route guard, tạo/quản lý PR, upload báo giá nhiều NCC, đối soát/sửa tay trích xuất (HITL-1), phân tích và đề xuất kèm lý do/nguồn, Quản lý duyệt/từ chối/yêu cầu chỉnh sửa, tạo PO                                          | ✅ Done | `src/api/routes/`, `src/application/`, `frontend/src/features/` (PR, quotations, comparison, purchaseOrders) | -    |
| Nguyễn Tiến Đạt        | Nối FE – BE – Agent và chạy happy case end-to-end (02–03/10), dùng extraction/decision model giả để kiểm chứng luồng                                                                                                                                             | ✅ Done | `docs/end-to-end-integration-results.md` (231 test pass tại thời điểm đó)                                    | -    |
| Nguyễn Mai Hoàng Thiện | Deploy bản MVP                                                                                                                                                                                                                                                   | ✅ Done | <https://c4-app-dotcom.duckdns.org/login>                                                                    | -    |

**Tổng kết ngày:** Có MVP chạy end-to-end: PR → upload báo giá → trích xuất → Buyer xác nhận → chuẩn hóa → TCO/so sánh/rủi ro → đề xuất có evidence → Quản lý duyệt → PO. Lưu ý: bản đăng nhập MVP dùng 2 tài khoản demo cố định, session lưu trong bộ nhớ tiến trình (30 phút).

---

## 2026-10-05 → 2026-10-11 (Tuần 4 · Tối ưu, đánh giá & xử lý lỗi)

| Member                                  | Task                                                                                                                                                                        | Status | Output                                                                                               | Time |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ | ---------------------------------------------------------------------------------------------------- | ---- |
| Nguyễn Thu Trang                        | Benchmark độ chính xác OCR/trích xuất trên bộ 19 báo giá có ground truth                                                                                                    | ✅ Done | `docs/benchmark_ocr.md`                                                                              | -    |
| Trần Mạnh Hùng                          | Tầng kiểm chứng sau Decision LLM: kiểm nguồn nguyên văn, Decimal replay, đối chiếu đơn vị/time origin, gates theo thứ tự; HITL-2 bền vững (version + idempotency key)       | ✅ Done | `src/application/evaluation/`, `src/infrastructure/evaluation/`, `docs/evaluation-implementation.md` | -    |
| Trần Mạnh Hùng                          | Tách OCR thành service nội bộ (HTTP), bỏ Paddle/Tesseract khỏi image core; hợp nhất Pydantic model về một root                                                              | ✅ Done | `ocr/`, `docs/optimization-v3/` (00 → 07)                                                            | -    |
| Nguyễn Thu Trang                        | Xử lý edge-case: PDF scan chất lượng thấp, bảng định dạng bất thường, thiếu thông tin/báo giá không đầy đủ (`needs_input`, `missing_fields`), khác UOM/tiền tệ (có mẫu GBP) | ✅ Done | `src/agents/tools/normalize_data.py`, `docs/state-machine.md`                                        | -    |
| Nguyễn Tiến Đạt                         | Chặn dữ liệu cũ/trùng: review bị stale trả `409`, retry không tạo PO trùng, phục hồi extraction đang chờ sau restart                                                        | ✅ Done | `tests/test_api/` (po\_approval, verified\_evaluation\_guards, procurement\_error\_states)           | -    |
| Nguyễn Mai Hoàng Thiện, Nguyễn Tiến Đạt | Hoàn thiện giao diện: luồng thao tác, bảng so sánh NCC, hiển thị claims/nguồn/trade-off, thông báo lỗi, fuzzy match tên hàng                                                | ✅ Done | `frontend/src/features/`, `frontend/src/*.test.ts` ,`src/agents/nodes/fuzzy_match.py`                | -    |
| Nguyễn Mai Hoàng Thiện, Nguyễn Tiến Đạt | Sửa lỗi phát hiện khi test, UI\_UX                                                                                                                                          | ✅ Done | `frontend/src/`                                                                                      | -    |

**Tổng kết ngày:** Sản phẩm đã ổn định hơn và sẵn sàng để nộp cho demoday.

---

---

```html
<!-- Format: copy block trên cho mỗi ngày làm việc -->
```
