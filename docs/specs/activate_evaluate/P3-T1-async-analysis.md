# P3-T1: POST analysis bất đồng bộ (202 + polling)

**Phase:** 3 | **Phụ thuộc:** Phase 1 xong | **Độ lớn:** lớn

## Mục tiêu
`POST /prs/{id}/analysis` hiện chờ cả quá trình gọi LLM, dễ timeout. Chuyển sang trả ngay và chạy nền.

## File liên quan
- `src/api/routes/procurement_workflow.py`
- `src/services/procurement_workflow.py`
- `frontend/features/comparison/comparison.js`, `frontend/core/api.js`

## Yêu cầu
1. `POST` tạo run ở trạng thái `running`, trả **202 Accepted** kèm `analysis_id`, rồi chạy graph nền. Chọn cơ chế đơn giản nhất phù hợp hạ tầng hiện có (ví dụ FastAPI `BackgroundTasks` hoặc thread/executor); nêu lựa chọn trong báo cáo.
2. Khi graph xong, cập nhật run với status cuối (`awaiting_review`, `repairable`, `needs_input`, `technical_failure`).
3. Frontend: sau POST, hiện "Đang phân tích" và poll `GET /prs/{id}/analysis` (mặc định 2 giây, backoff nhẹ, timeout tối đa cấu hình được). Dừng khi status khác `running`. Hủy polling khi người dùng rời màn hình.
4. Chống chạy trùng: nếu đã có run `running` cho cùng PR và cùng `snapshot_revision`, POST mới trả run hiện có thay vì tạo run mới.
5. Phục hồi: run `running` quá ngưỡng (mặc định 5 phút, cấu hình được) khi được đọc thì đánh dấu `technical_failure` kèm message.
6. Phân quyền và validation giữ nguyên như trước (role procurement, kiểm tra điều kiện `prepare()` trước khi nhận 202; lỗi đầu vào vẫn trả 4xx ngay).

## Ngoài phạm vi
Không đổi sang hàng đợi ngoài (Celery, Redis...). Không cache (P3-T2).

## Acceptance criteria
- POST trả về dưới 1 giây (với LLM mock chậm).
- FE tự cập nhật khi run xong, không cần reload.
- Bấm "Phân tích" hai lần liên tiếp chỉ tạo một run.
- Giả lập tiến trình chết giữa chừng: run kẹt `running` được chuyển `technical_failure` sau ngưỡng.

## Checklist tự kiểm tra
- Chạy test; mock LLM `sleep` 10 giây, đo thời gian POST.
- Thủ công: bấm phân tích, chuyển tab rồi quay lại, kiểm tra UI vẫn đúng trạng thái.
- Đọc diff: kiểm tra exception trong tác vụ nền được bắt và ghi vào run, không bị nuốt mất.
- Kiểm tra ghi SQLite từ tác vụ nền không gây lỗi khóa DB (đọc cách mở connection).

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
