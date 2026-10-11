# P1-T5: Test end-to-end luồng chuẩn

**Phase:** 1 | **Phụ thuộc:** P1-T4 | **Độ lớn:** vừa

## Mục tiêu
Khóa luồng chuẩn đã khôi phục bằng test tích hợp, để Phase 2 và 3 không làm hỏng.

## File liên quan
Thư mục test tích hợp của dự án; `src/api/routes/*`, `src/services/procurement_workflow.py`.

## Yêu cầu (LLM luôn mock)
1. Luồng chính: buyer `POST analysis` → run `awaiting_review` → `submit-approval` → manager `feedback approve` → draft PO tồn tại, PR và run `approved`, `evaluation.sqlite` có audit.
2. Nhánh Reject: manager reject → PR/run đúng trạng thái; không có PO. (Hành vi sau Reject hoàn thiện ở P2-T3, ở đây chỉ assert trạng thái hiện tại của code.)
3. Nhánh Revise: tương tự.
4. Snapshot đổi: sửa báo giá sau analysis → approve bị từ chối.
5. Idempotency: gửi cùng `idempotency_key` hai lần → chỉ một PO.
6. Phân quyền: procurement không gọi được `/feedback`; manager không gọi được `POST analysis`.
7. Test P1-T1 vẫn pass.

## Acceptance criteria
Toàn bộ test mới và cũ pass; không test nào phụ thuộc bypass.

## Checklist tự kiểm tra
- Chạy toàn bộ test suite, ghi lại số test pass/fail.
- Đọc test idempotency và snapshot: assert phải kiểm tra dữ liệu trong DB, không chỉ status code.
- Tạm đảo một điều kiện trong code (ví dụ bỏ `ensure_current()`), xác nhận test tương ứng fail rồi hoàn tác.

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
