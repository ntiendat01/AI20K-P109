# P2-T3: Hoàn thiện các trạng thái lỗi và luồng sửa

**Phase:** 2 | **Phụ thuộc:** P1-T3, P1-T4 (nên sau P2-T1, P2-T2) | **Độ lớn:** lớn

## Mục tiêu
Mọi trạng thái đều có đường đi tiếp cho người dùng; không có trạng thái "chết".

## Quyết định (mặc định)
Manager Reject: PR quay về `comparing`, run ghi lý do từ chối, buyer có thể phân tích lại. Nếu code đã có trạng thái PR dành cho từ chối, tái sử dụng nó và báo cáo.

## File liên quan
- `src/services/procurement_workflow.py`, `src/services/evaluation_workflow.py`
- `src/models/procurement_workflow.py`
- `frontend/features/comparison/comparison.js`, `frontend/features/approvals/approvals.js`
- tạo `docs/state-machine.md`

## Yêu cầu
| Status | Nguyên nhân | Buyer làm gì | UI |
|---|---|---|---|
| `needs_input` | Thiếu dữ liệu bắt buộc | Bổ sung báo giá/field | Danh sách field thiếu theo NCC, nút quay lại sửa báo giá |
| `repairable` | Proposal không đạt evaluation nhưng sửa được | Chạy lại | Hiện evaluation issues, nút "Chạy lại" |
| `technical_failure` | Lỗi LLM/hệ thống | Thử lại | Hiện message, nút "Thử lại" |
| Manager Revise | Manager yêu cầu sửa | Sửa báo giá/ghi chú, chạy lại | PR về `comparing`, hiện ghi chú manager |
| Manager Reject | Manager từ chối | Xem lý do, quyết định tiếp | Theo mục Quyết định |

1. Backend: mỗi chuyển trạng thái PR/run có kiểm tra tiền đề; trả lỗi 409 rõ ràng nếu sai trạng thái.
2. Backend: lưu ghi chú/lý do của manager và hiển thị qua `ProcurementAnalysis` (hoặc field phù hợp).
3. Frontend: mỗi trạng thái ở bảng có tiêu đề, nội dung và nút hành động như trên.
4. Viết `docs/state-machine.md` mô tả sơ đồ trạng thái PR và run (dạng bảng hoặc Mermaid), khớp với code.

## Ngoài phạm vi
Không tự động sửa dữ liệu báo giá bằng LLM. Không đổi cơ chế snapshot.

## Acceptance criteria
- Mỗi trạng thái ở bảng có ít nhất 1 test backend và 1 kịch bản kiểm tra thủ công cho FE.
- Từ bất kỳ trạng thái nào người dùng đều có hành động tiếp theo hợp lệ.
- `docs/state-machine.md` khớp với code (mọi chuyển trạng thái trong code có trong tài liệu và ngược lại).

## Checklist tự kiểm tra
- Chạy test BE; đọc `docs/state-machine.md` đối chiếu với code chuyển trạng thái (`grep -rn "status =" src/services/`).
- Thủ công: ép từng trạng thái (mock) và đi hết đường sửa tới khi về `awaiting_review`.
- Thử gọi chuyển trạng thái sai thứ tự bằng API, xác nhận nhận 409.

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
