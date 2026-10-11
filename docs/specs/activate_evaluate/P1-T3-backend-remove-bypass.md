# P1-T3: Backend bỏ `untrusted_proposal` và nhánh bypass

**Phase:** 1 | **Phụ thuộc:** P1-T2 | **Độ lớn:** vừa

## Mục tiêu
Backend không còn đường nào biến proposal thô thành PO. Mọi approve/reject/revise đi qua `EvaluationStore.review()`.

## Quyết định (mặc định, đổi trước khi giao nếu cần)
Run cũ đang ở `untrusted_proposal` khi migrate: đánh dấu `stale`. PR đang `pending_approval` của run đó được đưa về `comparing` để buyer phân tích lại.

## File liên quan
- `src/services/procurement_workflow.py` (`analyze()`, `submit-approval` logic, `feedback()`)
- `src/models/procurement_workflow.py` (enum/literal status)
- `src/api/routes/__init__.py` (submit approval), `src/api/routes/procurement_workflow.py`
- nơi lưu/migrate schema của `procurement-workflow.sqlite`

## Yêu cầu
1. `analyze()`: bỏ đoạn tự chuyển proposal không rỗng thành `untrusted_proposal`; status lấy từ kết quả `evaluate`.
2. `submit-approval`: chỉ chấp nhận `awaiting_review`. Giữ `ensure_current()`.
3. `feedback()`: xóa nhánh `TEMPORARY_UNTRUSTED_APPROVAL_BYPASS`. Approve/Reject/Revise đi qua `EvaluationStore.review()`; PO chỉ tạo từ recommendation đã được duyệt. Giữ kiểm tra recommendation version, snapshot, PR `pending_approval`, supplier thuộc snapshot, `idempotency_key`.
4. Xóa `untrusted_proposal` khỏi enum/literal/Pydantic model.
5. Migration tương thích ngược cho dữ liệu cũ theo mục Quyết định. Không xóa dữ liệu.
6. Response `ProcurementAnalysis` không trả `decision_proposal` khi run chưa verified (xem P1-T4 để khớp với frontend).

## Ngoài phạm vi
Không sửa frontend (T4). Không thêm trạng thái lỗi mới (P2-T3).

## Acceptance criteria
- Test của P1-T1 **pass**.
- `grep -rn "untrusted_proposal\|TEMPORARY_UNTRUSTED_APPROVAL_BYPASS" src/` chỉ còn trong migration hoặc test.
- Approve qua API trên run `awaiting_review` tạo draft PO và chuyển PR, run sang `approved`, có audit trong `evaluation.sqlite`.
- Sửa báo giá sau analysis thì approve bị từ chối do snapshot đổi.

## Checklist tự kiểm tra
- Chạy toàn bộ test BE, đặc biệt test P1-T1.
- Đọc diff của `feedback()`: không còn nhánh nào đọc `preferred_supplier_id` từ proposal thô để tạo PO.
- Sao lưu file `data/*.sqlite` trước khi chạy migration, chạy thử trên bản sao và kiểm tra run cũ được đánh dấu đúng.

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
