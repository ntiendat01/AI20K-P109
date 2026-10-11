# P3-T2: Cache theo `snapshot_revision` và cache evidence

**Phase:** 3 | **Phụ thuộc:** P3-T1 | **Độ lớn:** vừa

## Mục tiêu
Không chạy lại tool và LLM khi dữ liệu không đổi; không ingest lại evidence chunks cho file không đổi.

## Quyết định (mặc định)
Tài liệu cho biết `snapshot_revision` được tính từ PR, báo giá, file hash, policy **và ngày chạy**. Task này chỉ **điều tra và báo cáo** việc đó có chủ ý hay không, **chưa đổi cách tính hash**. Cache chỉ áp dụng khi `snapshot_revision` giống hệt.

## File liên quan
- `src/services/procurement_workflow.py` (`prepare()`, tính snapshot, ingest chunks)
- nơi lưu analysis run trong `procurement-workflow.sqlite`

## Yêu cầu
1. `analyze()`: nếu đã có run hợp lệ (không phải `technical_failure`, không `stale`) với cùng `pr_id` và `snapshot_revision` thì trả lại run đó, không gọi tool/LLM.
2. Cho phép ép chạy lại bằng tham số rõ ràng (ví dụ `?force=true`), chỉ role procurement.
3. Cache evidence chunks theo file hash: file đã ingest thì dùng lại.
4. Báo cáo: "ngày chạy" nằm ở đâu trong hash, hệ quả (analysis có bị coi là cũ khi sang ngày mới không), và đề xuất (không tự sửa).

## Ngoài phạm vi
Không đổi công thức snapshot. Không cache kết quả lỗi.

## Acceptance criteria
- Chạy analysis hai lần với dữ liệu không đổi: lần hai không gọi LLM (đếm call bằng mock), trả cùng `analysis_id`.
- Đổi một báo giá: chạy lại đầy đủ, `snapshot_revision` mới.
- `force=true` luôn chạy lại.
- Ingest chunks không lặp cho file hash đã có.

## Checklist tự kiểm tra
- Chạy test; xem số lần gọi mock LLM trong test cache.
- Đọc báo cáo về "ngày chạy" và tự quyết có đổi hash hay không (làm thành task riêng nếu muốn).
- Kiểm tra cache không trả run của PR khác (khóa phải gồm `pr_id`).

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
