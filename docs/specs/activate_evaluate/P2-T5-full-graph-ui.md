# P2-T5: Nối nhánh OCR/extraction vào UI (mặc định: không làm)

**Phase:** 2 | **Phụ thuộc:** cần bạn quyết định | **Độ lớn:** lớn

## Quyết định (mặc định)
**Không làm.** Nhánh `extract_documents → validate_extraction → confidence_router → human_review_extraction` hiện chưa có đường vào từ màn hình so sánh. Chỉ giao task này cho agent khi bạn xác định rõ nhánh này dùng ở màn hình nào.

## Nếu bạn không làm
Chỉ cần (tùy chọn) ghi vào tài liệu luồng: "Full graph chưa được nối vào UI; API hiện chỉ chạy `confirmed_input=True`."

## Nếu bạn muốn làm, hãy bổ sung trước khi giao agent
- Màn hình/điểm vào nào (upload báo giá ở đâu?).
- Cách hiển thị checkpoint `extraction_review` (interrupt của `human_review_extraction`).
- Ai được review (procurement hay manager).
- Cách resume graph sau khi người dùng xác nhận (cơ chế checkpoint/thread hiện có).

Sau khi có đủ thông tin, viết lại file này theo mẫu các task khác (Mục tiêu, File liên quan, Yêu cầu, Acceptance, Checklist).

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
