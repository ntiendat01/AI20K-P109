# P2-T2: Khôi phục strict validation, đánh dấu fallback

**Phase:** 2 | **Phụ thuộc:** P1-T2 | **Độ lớn:** vừa

## Mục tiêu
VAT, phí phụ, lead time, warranty đang bị lấp bằng fallback im lặng, làm TCO và so sánh sai mà không ai biết. Cần chặn hoặc cảnh báo rõ.

## Quyết định (mặc định)
Thiếu field bắt buộc → trả `needs_input` kèm danh sách field thiếu theo từng NCC, **không** dùng fallback. (Phương án thay thế: cho phép fallback bằng cờ cấu hình, ghi vào `fallbacks_applied` và `uncertainties`. Chỉ làm nếu bạn đổi quyết định.)

## File liên quan
- `src/services/procurement_workflow.py` (`prepare()`)
- `src/agents/nodes/normalize.py`
- `src/models/procurement.py` (`RawExtraction`, `TCOResult`)
- `src/models/procurement_workflow.py`

## Yêu cầu
1. Bỏ comment và khôi phục các strict validation cho VAT (`vat_rate`/`vat_included`), phí phụ, `lead_time_days`, `warranty_months`.
2. Khi thiếu: `prepare()` không chạy graph; trả run `needs_input` với `message` và cấu trúc `missing_fields` dạng `[{supplier_id, supplier_name, fields: [...]}]`.
3. Xóa các giá trị fallback tạm (liệt kê trong báo cáo những chỗ đã xóa).
4. `TCOResult.status` và `missing_fields` phản ánh đúng dữ liệu thiếu nếu thiếu lọt qua tới tool.
5. Giữ các kiểm tra hiện có: ≥2 báo giá, tất cả confirmed, tên và `supplier_id` không trùng.

## Ngoài phạm vi
Không sửa UI bổ sung dữ liệu (làm ở P2-T3). Không đổi công thức TCO.

## Acceptance criteria
- Với từng field thiếu (VAT, phí, lead time, warranty), analysis trả `needs_input` đúng field và đúng NCC; LLM không được gọi.
- Dữ liệu đầy đủ thì chạy bình thường, kết quả TCO không đổi so với trước.
- Không còn giá trị fallback ngầm trong `prepare()`/`normalize`.

## Checklist tự kiểm tra
- Đọc diff, tìm các giá trị mặc định đã bị xóa (ví dụ `0.1`, `0`, `None` được gán thay thế).
- Chạy test; tự tạo một báo giá thiếu lead time và xác nhận API trả `needs_input`.
- Chạy lại bộ dữ liệu mẫu hiện có: kết quả TCO giống trước.

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
