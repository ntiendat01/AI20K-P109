# P1-T2: Bật lại node `evaluate` trong graph

**Phase:** 1 | **Phụ thuộc:** P1-T1 | **Độ lớn:** nhỏ-vừa

## Mục tiêu
Sau `decision_llm`, proposal phải đi qua `evaluate` và được lưu vào `evaluation.sqlite` để tạo verified review.

## File liên quan
- `src/agents/graph.py`
- node evaluate (`src/agents/nodes/`), `src/services/evaluation.py`, `src/services/evaluation_workflow.py`
- `src/models/evaluation.py`

## Yêu cầu
1. Trong `graph.py`: khôi phục `graph.add_edge("decision_llm", "evaluate")` và `graph.add_edge("evaluate", END)`; xóa `graph.add_edge("decision_llm", END)`. Xóa comment `TEMPORARY ... BYPASS` liên quan.
2. Node `evaluate`: lấy `decision_proposal`, lấy `RuntimeEvaluationContext` từ application, gọi `EvaluationWorkflow.submit()`, trả `evaluation_result`, `workflow_status`, `recommendation_id`, `recommendation_version`.
3. Nếu `decision_proposal` rỗng: không gọi `submit()`; trả `workflow_status` báo lỗi kỹ thuật (hành vi chi tiết hoàn thiện ở P2-T1). Không để proposal rỗng đi tiếp như thành công.
4. Đảm bảo `ProcurementWorkflow.analyze()` đọc đúng các field mới từ state sau khi graph chạy.

## Ngoài phạm vi
Không sửa `feedback()`, `submit-approval` hay frontend (làm ở T3, T4).

## Acceptance criteria
- Sau analysis với dữ liệu hợp lệ, `evaluation.sqlite` có proposal version và evaluation result.
- State cuối của graph có `recommendation_id`, `recommendation_version`, `workflow_status`.
- Graph không còn đường nào từ `decision_llm` thẳng đến END.

## Test
Test graph với LLM mock trả proposal hợp lệ: kiểm tra `submit()` được gọi một lần và state có đủ field. Test proposal rỗng: `submit()` không được gọi.

## Checklist tự kiểm tra
- `git diff src/agents/graph.py`: đúng 2 edge được bật, 1 edge bị xóa.
- `grep -rn "decision_llm.*END" src/agents/`: không còn.
- Chạy test graph; chạy thử analysis thật với dữ liệu mẫu và mở `data/evaluation.sqlite` xem có bản ghi mới.
- Lưu ý: sau task này, frontend và nhánh bypass backend có thể tạm không khớp với status mới cho tới khi xong T3 và T4. Đó là bình thường.

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
