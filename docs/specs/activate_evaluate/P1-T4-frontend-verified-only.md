# P1-T4: Frontend chỉ hiện điều khiển khi có verified review

**Phase:** 1 | **Phụ thuộc:** P1-T3 | **Độ lớn:** vừa

## Mục tiêu
UI khớp với backend mới: nút phê duyệt chỉ xuất hiện khi có verified review.

## Quyết định (mặc định)
Bỏ hẳn raw proposal khỏi UI, không có chế độ debug.

## File liên quan
- `frontend/features/comparison/comparison.js`
- `frontend/features/approvals/approvals.js`
- `frontend/core/api.js`

## Yêu cầu
1. Xóa khối "Phê duyệt tạm thời", cảnh báo "chưa qua evaluation hoặc human review" và mọi nhánh render theo `untrusted_proposal`.
2. Nút Approve/Reject/Revise của manager chỉ hiện khi `run.status === "awaiting_review"` và PR là `pending_approval`; dữ liệu lấy từ `GET /recommendations/{id}/review`.
3. Nút "Gửi Quản lý phê duyệt": chỉ khi `awaiting_review` và PR là `comparing`.
4. Nút "Phân tích bằng Agent": giữ điều kiện cũ (PR là `comparing` hoặc `awaiting_quotation`, role procurement).
5. Render theo `run.status` đúng bảng sau (các trạng thái lỗi chi tiết hoàn thiện ở P2-T3):

| run.status | Tiêu đề |
|---|---|
| not_started | Chưa phân tích |
| running | Đang phân tích |
| awaiting_review | Đề xuất đã kiểm chứng |
| repairable | Đề xuất cần sửa |
| needs_input | Cần bổ sung dữ liệu |
| technical_failure | Phân tích chưa thành công |
| approved | Đã duyệt (link PO) |

## Ngoài phạm vi
Không thiết kế lại giao diện; không thêm luồng sửa (P2-T3).

## Acceptance criteria
- Không còn text hay logic `untrusted` trong thư mục `frontend/`.
- Với mỗi status ở bảng trên và mỗi role (procurement, manager), UI hiển thị đúng tiêu đề, dữ liệu và nút.
- Không có nút phê duyệt ở bất kỳ trạng thái nào khác `awaiting_review`.

## Checklist tự kiểm tra (thủ công)
- `grep -rn "untrusted" frontend/`: không còn.
- Chạy app, đăng nhập lần lượt procurement và manager, đi qua: chưa phân tích → đang phân tích → awaiting_review → gửi duyệt → manager thấy nút → approve → chuyển sang PO.
- Thử manager mở PR ở trạng thái `comparing`: không có nút phê duyệt.
- Mở DevTools, kiểm tra không có request tới `/review` khi status không phải `awaiting_review`.

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
