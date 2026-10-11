# P3-T5: Nhất quán giữa hai SQLite

**Phase:** 3 | **Phụ thuộc:** P3-T1 | **Độ lớn:** vừa-lớn

## Mục tiêu
`procurement-workflow.sqlite` và `evaluation.sqlite` được ghi riêng, có nguy cơ lệch trạng thái (ví dụ PR đã approved nhưng recommendation chưa cập nhật). Cần thứ tự ghi rõ ràng và cách phát hiện/phục hồi.

## File liên quan
- `src/services/procurement_workflow.py`
- `src/services/evaluation_workflow.py`, `src/services/evaluation.py`
- tạo `docs/consistency.md`

## Yêu cầu
1. Liệt kê mọi điểm ghi vào cả hai DB (analysis, submit-approval, feedback/approve, tạo PO) trong `docs/consistency.md`.
2. Quy định thứ tự ghi cho từng điểm và lý do (ví dụ ghi evaluation trước, procurement sau, và thao tác sau phải idempotent để retry an toàn).
3. Đảm bảo retry với cùng `idempotency_key` sau lỗi giữa chừng không tạo PO trùng và hoàn tất được phần còn thiếu.
4. Thêm lệnh/hàm đối soát (script hoặc hàm gọi tay) phát hiện lệch: PR `approved` mà recommendation chưa approved, run `awaiting_review` mà không có recommendation, PO không có recommendation, v.v. Chỉ báo cáo, không tự sửa dữ liệu.
5. Thêm test mô phỏng lỗi giữa chừng (ví dụ ném lỗi sau khi tạo PO nhưng trước khi cập nhật recommendation) rồi retry.

## Ngoài phạm vi
Chuyển sang Postgres hoặc đổi sang một DB chung. Chỉ ghi vào backlog nếu cần nhiều người dùng đồng thời.

## Acceptance criteria
- `docs/consistency.md` mô tả đủ điểm ghi và thứ tự.
- Test lỗi giữa chừng + retry pass: không có PO trùng, trạng thái cuối nhất quán.
- Hàm đối soát chạy được trên DB mẫu và liệt kê đúng các lệch được tạo cố ý trong test.

## Checklist tự kiểm tra
- Đọc `docs/consistency.md` đối chiếu với code.
- Chạy test lỗi giữa chừng; tạm xóa kiểm tra idempotency và xác nhận test fail, rồi hoàn tác.
- Chạy hàm đối soát trên bản sao DB thật của bạn, xem có lệch cũ không.

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
