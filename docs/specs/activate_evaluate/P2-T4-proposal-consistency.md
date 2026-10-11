# P2-T4: Kiểm tra nhất quán proposal trong `evaluate`

**Phase:** 2 | **Phụ thuộc:** P1-T2 | **Độ lớn:** vừa

## Mục tiêu
Proposal không chỉ đúng schema mà còn phải nhất quán nội bộ và khớp dữ liệu tool.

## File liên quan
- `src/services/evaluation.py`, `src/services/evaluation_workflow.py`
- `src/models/evaluation.py`

## Yêu cầu
Đọc phần kiểm tra hiện có của `EvaluationWorkflow`. Với mỗi điều kiện dưới đây, nếu chưa được kiểm tra thì bổ sung, nếu đã có thì chỉ thêm test:
1. Mọi `supporting_claim_ids`, `rationale_claim_ids`, `comparison_ids`, `trade_off_ids`, `risk_ids`, `uncertainty_ids` tham chiếu tới phần tử tồn tại.
2. Số liệu trong claim khớp `tco_results` (so với tool deterministic).
3. `decision.preferred_supplier_id` trùng `ranked[0].supplier_id` và thuộc `candidate_ids`.
4. `ranked` không trùng supplier; số phần tử phù hợp `top_n`, nếu thiếu NCC thì có `shortfall`.
5. Mỗi vi phạm cho ra issue có mã/lý do rõ ràng và kết quả `repairable` (hoặc từ chối) đúng như thiết kế hiện tại.

## Ngoài phạm vi
Không đổi schema `DecisionProposal`. Không đổi prompt.

## Acceptance criteria
Với proposal cố tình sai từng điều kiện 1-5, evaluation phát hiện đúng và báo đúng lý do. Proposal đúng vẫn qua.

## Checklist tự kiểm tra
- Đếm test mới: ít nhất 1 test cho mỗi điều kiện.
- Chạy toàn bộ test evaluation, đảm bảo test cũ không vỡ.
- Đọc diff: các kiểm tra mới không làm từ chối nhầm proposal hợp lệ (xem fixture proposal đúng).

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
