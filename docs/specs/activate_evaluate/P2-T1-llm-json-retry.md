# P2-T1: Retry/repair khi Decision LLM trả JSON hỏng

**Phase:** 2 | **Phụ thuộc:** P1-T2 | **Độ lớn:** vừa

## Mục tiêu
Hiện tại parse lỗi chỉ ghi log rồi trả `decision_proposal = {}`. Cần retry, và nếu vẫn lỗi thì báo `technical_failure` rõ ràng.

## Quyết định (mặc định)
Structured output/JSON mode của Groq: chỉ bật nếu xác minh được model đang dùng hỗ trợ (đọc tài liệu provider hoặc thử có kiểm soát). Nếu không chắc, giữ JSON thường.

## File liên quan
- `src/agents/nodes/decision_llm.py`
- `src/models/evaluation.py` (`DecisionProposal`)
- `src/agents/state.py`, `src/agents/graph.py` (routing sau node)

## Yêu cầu
1. Khi response không parse được JSON hoặc không qua validate `DecisionProposal`: retry tối đa 2 lần. Mỗi lần gửi thêm thông báo lỗi ngắn gọn (lỗi parse hoặc các field vi phạm) để model tự sửa. Giữ nguyên system prompt và payload gốc.
2. Nếu vẫn lỗi sau các lần thử: set state `workflow_status = "technical_failure"` kèm `message` thân thiện cho buyer (tiếng Việt, không lộ stack trace). Không trả `{}` như thành công. Graph định tuyến thẳng tới END, không gọi `evaluate`.
3. Log chẩn đoán: số lần thử, loại lỗi, độ dài response. Không log nội dung báo giá đầy đủ.
4. Số lần retry và timeout lấy từ cấu hình, có giá trị mặc định.
5. `ProcurementWorkflow.analyze()` lưu run với status `technical_failure` và `message` này để frontend hiển thị.

## Ngoài phạm vi
Không đổi provider, không đổi nội dung system prompt (trừ phần thêm thông báo lỗi khi retry).

## Acceptance criteria
- Mock LLM: lỗi lần 1, đúng lần 2 → thành công, `retry_count = 1`.
- Mock LLM: lỗi 3 lần → `technical_failure`, có `message`, `evaluate` không được gọi, không có proposal rỗng được lưu như thành công.
- Số lần gọi LLM không vượt quá 1 + số retry cấu hình.

## Checklist tự kiểm tra
- `git diff src/agents/nodes/decision_llm.py`: vòng retry có giới hạn, không có vòng lặp vô hạn.
- Chạy test mới; thử thủ công bằng cách ép mock trả chuỗi rác và xem UI hiện "Phân tích chưa thành công".

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
