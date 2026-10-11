# P3-T3: Observability (events và log có cấu trúc)

**Phase:** 3 | **Phụ thuộc:** P3-T1 (độc lập với T2) | **Độ lớn:** vừa

## Mục tiêu
Có đủ dữ liệu để debug và đo chất lượng: thời lượng từng node, token/chi phí LLM, lỗi, số lần retry.

## File liên quan
- `src/services/procurement_workflow.py` (tạo `events`)
- `src/agents/nodes/decision_llm.py` (và các node khác nếu cần)
- `src/models/procurement_workflow.py` (schema `events`)
- cấu hình logging hiện có

## Yêu cầu
1. Mỗi event node gồm: `node`, `started_at`, `duration_ms`, `status` (`ok`/`error`), `error` (nếu có), `retry_count` (nếu có). Giữ tương thích với field `node` và `at` cũ nếu frontend đang đọc.
2. Với `decision_llm`: thêm `model`, `prompt_tokens`, `completion_tokens`, `latency_ms`. Nếu provider không trả token, ghi `null` thay vì đoán.
3. Log JSON có cấu trúc kèm `pr_id`, `analysis_id`, `recommendation_id` ở các điểm: bắt đầu/kết thúc analysis, mỗi node, lỗi, retry.
4. Không log token xác thực, không log nội dung báo giá đầy đủ.
5. Không thêm dashboard hay hệ thống ngoài.

## Ngoài phạm vi
Metrics server, tracing phân tán, thay đổi UI.

## Acceptance criteria
- Một run mẫu có `events` đầy đủ trường như trên.
- Log của một run cho phép truy vết toàn bộ bằng `analysis_id`.
- Test kiểm tra cấu trúc `events` và việc thiếu token không làm lỗi.

## Checklist tự kiểm tra
- Chạy một analysis mẫu, đọc `events` trong response/DB và log.
- `grep` log mẫu xem có lộ `Bearer` hay nội dung báo giá không.
- Xác nhận frontend vẫn chạy đúng (không phụ thuộc vào định dạng cũ của `events`).

---

## Quy tắc chung (bắt buộc với agent)

- **Không chạy** `git commit`, `git push`, `git checkout -b`, `git stash`, `git reset`. Chỉ sửa file trong working tree; người dùng sẽ tự review và push.
- Chỉ sửa trong phạm vi task này. Nếu thấy cần sửa ngoài phạm vi, dừng lại và báo, không tự làm.
- Spec được viết từ tài liệu mô tả luồng, **chưa đối chiếu code thực tế**. Đọc code liên quan trước. Nếu giả định sai, nói rõ và điều chỉnh tối thiểu.
- Không refactor lan man, không đổi hành vi nằm ngoài task.
- Invariant của hệ thống: output thô của Decision LLM không bao giờ được tạo PO; LLM chỉ đề xuất, TCO do tool deterministic tính; không trả `context` và `quotations` ra frontend.
- Không ghi token xác thực hay nội dung báo giá đầy đủ vào log.
- Khi xong, báo cáo gồm: (1) danh sách file đã thêm/sửa, (2) giả định đã xác nhận hoặc bác bỏ, (3) lệnh đã chạy và kết quả test, (4) việc còn dở hoặc rủi ro.

## Bối cảnh chung

Luồng: `Frontend (comparison.js) → FastAPI /api/v1 → ProcurementWorkflow → LangGraph (normalize → check_data_ready → decision_llm → END)`.
Hiện có 2 bypass tạm thời (comment `TEMPORARY ... BYPASS`): (1) edge `decision_llm → evaluate → END` bị comment, run có status `untrusted_proposal`; (2) `ProcurementWorkflow.feedback()` có nhánh `TEMPORARY_UNTRUSTED_APPROVAL_BYPASS` tạo PO thẳng từ `decision.preferred_supplier_id`. Strict validation cho VAT, phí phụ, lead time, warranty đang bị comment và dùng fallback. Dữ liệu lưu ở `data/procurement-workflow.sqlite` (analysis run, snapshot, PO command) và `data/evaluation.sqlite` (verified flow).
File nguồn chính: `src/agents/graph.py`, `src/agents/nodes/decision_llm.py`, `src/services/procurement_workflow.py`, `src/services/evaluation.py`, `src/services/evaluation_workflow.py`, `src/api/routes/procurement_workflow.py`, `src/api/routes/__init__.py`, `src/models/*.py`, `frontend/core/api.js`, `frontend/features/comparison/comparison.js`, `frontend/features/approvals/approvals.js`.
