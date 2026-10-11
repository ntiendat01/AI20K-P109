# P1-T1: Test bảo vệ "raw LLM không tạo được PO"

**Phase:** 1 | **Phụ thuộc:** không | **Độ lớn:** nhỏ

## Mục tiêu
Có một test chốt chặn trước khi gỡ bypass, để chứng minh output thô của Decision LLM không thể tạo PO. Test này **sẽ fail** trên code hiện tại (vì bypass đang bật). Nó là mốc hoàn thành cho cả Phase 1.

## File liên quan
- `src/services/procurement_workflow.py` (`feedback()`)
- `src/api/routes/procurement_workflow.py`
- thư mục test hiện có của dự án (đặt test cạnh các test của workflow)

## Yêu cầu
1. Test A: tạo run có `decision_proposal` thô (chưa qua `evaluate`, không có bản ghi trong `evaluation.sqlite`), PR ở `pending_approval`. Gọi `POST /recommendations/{id}/feedback` với `decision = approve` bằng token manager. Kỳ vọng: bị từ chối (4xx), **không có PO nào được tạo**, PR và run không đổi trạng thái.
2. Test B: kiểm tra mọi code path tạo PO (tìm hàm lưu draft PO) chỉ được gọi khi recommendation tương ứng đã ở trạng thái verified/được duyệt trong `evaluation.sqlite`. Có thể là test hành vi (gọi qua API với nhiều trạng thái run) thay vì phân tích tĩnh.
3. Dùng fixture/mock có sẵn của dự án; không gọi LLM thật.
4. Đánh dấu test bằng comment ghi rõ: "expected to fail until P1-T3".

## Ngoài phạm vi
Không sửa code production trong task này.

## Acceptance criteria
- Test tồn tại và chạy được.
- Chạy trên code hiện tại thì fail, và lý do fail là PO bị tạo hoặc request không bị từ chối (không phải lỗi setup).

## Checklist tự kiểm tra
- `git diff --stat`: chỉ có file test mới/sửa, không có file production.
- Chạy riêng test mới, xác nhận fail và đọc thông báo fail xem đúng lý do.
- Đọc test: có assert "không có PO" và "trạng thái không đổi" chứ không chỉ assert status code.

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
