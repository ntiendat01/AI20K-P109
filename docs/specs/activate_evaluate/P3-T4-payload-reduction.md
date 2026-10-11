# P3-T4: Giảm payload gửi LLM

**Phase:** 3 | **Phụ thuộc:** P2-T4 (cần evaluate đủ chặt để đo chất lượng) | **Độ lớn:** vừa

## Mục tiêu
Giảm token mỗi lần gọi Decision LLM mà không làm giảm chất lượng đề xuất.

## File liên quan
- `src/agents/nodes/decision_llm.py` (`_with_decision_context()`, dựng payload)
- `src/models/evaluation.py` (schema)

## Yêu cầu
1. Đo baseline số token (prompt) với 2, 5, 10 NCC bằng dữ liệu mẫu; ghi bảng vào báo cáo.
2. Rút gọn payload: bỏ trường null/rỗng, bỏ chi tiết mà LLM không dùng (ví dụ `items_tco` chi tiết nếu proposal không tham chiếu), rút gọn phần mô tả thừa trong schema.
3. Giữ nguyên contract `DecisionProposal` (10 nhóm field) và giữ nguyên mọi số liệu mà claim cần tham chiếu.
4. Không thay system prompt về ý nghĩa.
5. So sánh trước/sau: số token, tỷ lệ proposal qua `evaluate`, tỷ lệ parse lỗi trên cùng bộ dữ liệu mẫu (dùng LLM thật nếu bạn cho phép, nếu không báo rõ chưa đo được chất lượng).

## Ngoài phạm vi
Đổi model, đổi schema, đổi cách tính TCO.

## Acceptance criteria
- Token giảm so với baseline (ghi rõ phần trăm cho 2/5/10 NCC).
- Tỷ lệ proposal qua evaluate không giảm trên bộ mẫu.
- Test hiện có vẫn pass.

## Checklist tự kiểm tra
- Đọc bảng baseline và kết quả sau, kiểm tra số liệu hợp lý.
- Xem payload mới bằng log debug: vẫn có đủ `tco_results`, `comparison_matrix`, `risk_flags`, `confirmed_context`.
- Tự chạy 3-5 lần với LLM thật trên dữ liệu mẫu, so sánh chất lượng bằng mắt.

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
