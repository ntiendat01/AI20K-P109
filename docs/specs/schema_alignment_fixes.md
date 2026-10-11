# Spec: Khớp code runtime với schema mới (models_v1)

Trạng thái: **DRAFT — chờ duyệt**. Nguồn: rà soát code ngày 2026-10-07.
Phạm vi: sửa các chỗ code/dữ liệu/test còn lệch so với `src/models_v1` và pipeline mới, gây lỗi khi chạy sản phẩm.
Ngoài phạm vi: đổi `src/models_v1/**`, đổi contract trong `specs/contracts/**`, đổi prompt, đổi công thức `calculate_tco`/`compare_suppliers` (trừ khi mục tương ứng được duyệt).

## Quy ước
- Mỗi mục = tối đa 1 commit, kèm test và lệnh kiểm chứng.
- Mục đánh dấu **CẦN QUYẾT** chưa được triển khai cho đến khi chủ dự án chọn phương án.
- Không xóa/skip/nới assert test để cho qua; chỉ cập nhật test khi hành vi mới đã được duyệt.
- Test không được gọi LLM/mạng thật.

---

## Nhóm A — Lỗi chắc chắn gây hỏng khi chạy

### A1. Run cũ `awaiting_review` làm GET analysis trả 500
- **Hiện trạng:** `procurement-workflow.sqlite` có run mới nhất của 2 PR ở trạng thái `awaiting_review`. Giá trị này không nằm trong `WorkflowStatus` (`src/models/old/procurement_workflow.py`) nên `ProcurementAnalysis.model_validate` lỗi → `GET /prs/{id}/analysis` 500.
- **Yêu cầu:**
  1. `ProcurementWorkflow.migrate_legacy_runs` (`src/services/procurement/workflow.py`) chuyển mọi run `awaiting_review` sang `stale` với message "Đề xuất cũ chưa được kiểm chứng. Hãy phân tích lại trước khi gửi duyệt.", giữ nguyên payload audit, và gọi `prs.reset_stale_approval` nếu đó là run mới nhất của PR (giống nhánh `untrusted_proposal`).
  2. Hàm idempotent; chạy lại không đổi gì thêm.
  3. `public_run` (`src/api/routes/procurement_workflow.py`) không được để một status lạ làm response 500: status ngoài `WorkflowStatus` được ánh xạ sang `stale` ở biên response (không ghi ngược DB).
- **File:** `src/services/procurement/workflow.py`, `src/api/routes/procurement_workflow.py`.
- **Test:** thêm vào `tests/test_api/test_procurement_workflow_route.py`: (a) DB có run `awaiting_review` → sau khởi tạo service, `latest()` trả `stale`; (b) route analysis trả 200 với status `stale`; (c) chạy migrate 2 lần cho cùng kết quả.
- **Kiểm chứng:** `pytest tests/test_api/test_procurement_workflow_route.py -q`.

### A2. Endpoint cũ luôn trả 409
- **Hiện trạng:** `POST /prs/{id}/submit-approval`, `/approve`, `/reject` trong `src/api/routes/__init__.py` (khoảng dòng 241, 293, 325) so sánh `status == "awaiting_review"`; workflow giờ chỉ sinh `awaiting_buyer_review`/`pending_manager_approval`. UI mới không gọi các endpoint này.
- **Phương án (CẦN QUYẾT):**
  - **P1 (khuyến nghị):** gỡ 3 endpoint cũ khỏi router; cập nhật/xóa test gọi chúng. Luồng chính thức: `/analyses/{id}/submit-approval` và `/recommendations/{id}/feedback`.
  - **P2:** giữ làm alias: `submit-approval` ↔ trạng thái `awaiting_buyer_review`; `approve`/`reject` ↔ `pending_manager_approval`, ủy quyền cho cùng service như route mới.
- **Test:** P1: test xác nhận 3 route trả 404/405. P2: test happy path và 409 khi sai trạng thái.
- **Kiểm chứng:** `pytest tests/test_api/test_po_approval.py tests/test_api/test_pr.py -q`.

### A3. Buyer không xác nhận được báo giá khi chế độ AI bỏ bớt dòng
- **Hiện trạng:** `_project_v1_draft` (`src/services/quotation/intake.py`) lọc dòng qua `_review_item`: bỏ dòng có số lượng lẻ, thiếu đơn giá, hoặc đơn giá quá 2 chữ số thập phân (vì `QuotationItem` cũ ép `quantity: int`). `agent_extractions` (`lines`) vẫn giữ đủ dòng. `resume_confirmation` đòi `len(payload.items) == len(agent_extractions)` nên Buyer bị lỗi "Số dòng xác nhận cần khớp…".
- **Yêu cầu:** số dòng hiển thị cho Buyer và số dòng lưu trong `agent_extractions` phải luôn tương ứng 1-1, hoặc việc ghép phải dựa trên `source_item_id` thay vì độ dài danh sách.
  - Dòng không chuyển được sang `QuotationItem` cũ không bị bỏ im lặng: hoặc giữ lại ở dạng nháp để Buyer sửa (số lượng lẻ làm tròn không được tự ý), hoặc đưa vào `warnings` kèm `source_item_id`, và `agent_extractions` chỉ giữ các dòng tương ứng với dòng hiển thị.
  - Không đổi `src/models_v1` hay model `QuotationItem` cũ trong mục này. Nếu cần hỗ trợ số lượng lẻ thật sự thì tách thành quyết định riêng (xem C2).
- **File:** `src/services/quotation/intake.py`, có thể `src/services/quotation/repository.py` (`apply_agent_extraction`, `confirm`).
- **Test (thêm vào `tests/test_api/test_quotations.py`):** draft có 3 dòng, trong đó 1 dòng số lượng `2.5` và 1 dòng thiếu đơn giá → (a) `extract_for_quotation` trả `items` và `agent_extractions` khớp nhau; (b) confirm với đúng các dòng hiển thị thành công; (c) có warning nêu rõ dòng bị loại.
- **Kiểm chứng:** `pytest tests/test_api/test_quotations.py tests/test_api/test_extraction.py -q`.

---

## Nhóm B — Test và script đã lệch schema

### B1. Test import hàm không còn tồn tại
- `tests/test_agents/test_decision_payload.py` import `build_decision_payload`, `build_legacy_decision_payload`, `estimate_payload_tokens`; `tests/test_agents/test_decision_proposal_retry.py` import `BUYER_DECISION_FAILURE_MESSAGE`, `decision_proposal` từ `src.agents.nodes.decision_llm`.
- **Yêu cầu:** với mỗi test, ghi rõ trong PR: còn hành vi tương ứng trong `decision_llm` mới hay không. Còn → viết lại theo API mới (`decision_llm(state, llm=...)`, `DecisionProposal` 6 trường). Không còn → xóa test **kèm lý do được duyệt** (CẦN DUYỆT, vì đây là xóa test). Không được để file gây lỗi collection.
- **Kiểm chứng:** `pytest tests/test_agents -q` không có lỗi collection.

### B2. Test còn assert `awaiting_review`
- Các file: `tests/test_api/test_po_approval.py`, `test_verified_evaluation_guards.py`, `test_procurement_integration.py`, `test_phase3_operability.py` (và bất kỳ nơi nào grep ra).
- **Yêu cầu:** cập nhật theo luồng mới: `awaiting_buyer_review` → Buyer submit → `pending_manager_approval` → Manager approve → `approved`. Assert về hành vi (trạng thái, PO được tạo một lần, idempotent) giữ nguyên độ chặt; không nới.
- Test dùng fixture `tests/fixtures/procurement_integration.py` phải sinh proposal đúng shape `DecisionProposal` (status, preferred_supplier_id, ranked_supplier_ids, rationale, tradeoffs, input_artifact_ids).
- **Kiểm chứng:** `pytest tests/test_api -q`.

### B3. Test phụ thuộc ngày
- `tests/test_boundary_extraction_flow_v1.py::test_tc_flow09...` dùng `date.today() + timedelta(days=5)` rồi so với số ngày làm việc → kết quả đổi theo thứ trong tuần.
- **Yêu cầu:** cố định ngày (monkeypatch `date.today` hoặc dùng ngày hạn tuyệt đối cùng một ngày "hôm nay" giả) để test xác định. Giữ assert `len(risk_flags) == 1`.
- **Kiểm chứng:** chạy test với 7 giá trị "hôm nay" khác nhau (parametrize) đều pass.

### B4. Script smoke import module cũ
- `scripts/smoke_procurement_live.py` import `src.services.purchase_orders`, `purchase_requests`, `quotations` (đã chuyển sang `src.services.procurement.*` / `src.services.quotation.*`).
- **Yêu cầu:** sửa đường dẫn import; script phải chạy được `python -c "import ast;ast.parse(open('scripts/smoke_procurement_live.py').read())"` và `python scripts/smoke_procurement_live.py --help` (hoặc tương đương) không lỗi import.

---

## Nhóm C — Quyết định nghiệp vụ (CẦN QUYẾT trước khi code)

### C1. Phí vận chuyển trong TCO
- **Hiện trạng:** `calculate_tco` luôn đặt `surcharges = 0`; `prepare()` vẫn bắt buộc `shipping_fee` và PO cộng phí ship. Xếp hạng theo TCO không có ship, tổng PO có ship.
- **Phương án:**
  - **P1:** giữ TCO không gồm ship (đúng contract: shipping chưa chốt, không mặc định 0); bỏ `shipping_fee` khỏi `REQUIRED_QUOTATION_FIELDS`; PO ghi `shipping_amount = null` khi chưa có; UI ghi rõ "chưa gồm phí giao hàng".
  - **P2:** đưa ship vào `surcharges` của TCO (CẦN DUYỆT thay đổi contract/công thức, và đáp án `calculate_tco` đổi → phải chạy lại toàn bộ test TCO và cập nhật có kiểm soát).
  - **P3:** giữ nguyên hiện trạng nhưng ghi rõ giới hạn trong UI/tài liệu.
- Sau khi chọn, viết test: tổng PO == TCO được dùng để xếp hạng (P2) hoặc PO không cộng ship khi `null` (P1).

### C2. Số lượng lẻ
- `QuotationItem` cũ chỉ nhận `int`; `models_v1` nhận `Decimal > 0`. Chọn: (a) giữ `int`, xử lý ở A3; (b) đổi `QuotationItem` cũ sang `Decimal` (đổi schema lưu `data/quotations.json` và PO → **CẦN DUYỆT**, kèm kế hoạch migrate).

### C3. VAT khi giá đã gồm VAT
- **Hiện trạng:** `total_vat = 0` và `vat_included` bị gán cứng `False` ở `_public_tco_item`, nên cột VAT trên UI sai với báo giá đã gồm VAT.
- **Phương án:** (a) chỉ sửa lớp hiển thị: truyền `vat_included` thật và tính VAT tách ra để hiển thị, không đổi số TCO; (b) sửa `calculate_tco` để tách VAT khỏi giá gồm VAT (đổi đáp án → CẦN DUYỆT). Khuyến nghị (a).
- **Test:** báo giá `vat_included=true`, giá 110.000, VAT 10% → UI/response hiển thị VAT 10.000, tổng 110.000, `calculate_tco` không đổi.

### C4. Manager approve / revise / reject
- **Hiện trạng:** với `pending_manager_approval`, mọi quyết định khác `approve` bị 409 ("chỉ hỗ trợ phê duyệt tạm thời"); UI ẩn nút reject/revise khi proposal `proposed`. Contract (`specs/contracts/domain-and-storage.md`) có `ApprovalDecision: approve | revise | reject`, `reason` bắt buộc khi revise/reject.
- **Phương án:** (a) giữ tạm, ghi rõ giới hạn và thêm test khóa hành vi; (b) triển khai reject/revise theo `ManagerDecisionRequest` (reject → PR `rejected`, không tạo PO; revise → lưu `pending_feedback`, quay lại phân tích). Nếu chọn (b), tách thành task riêng có plan riêng.

---

## Nhóm D — Cải thiện nhỏ

### D1. Giải trình dùng tên NCC thay vì UUID
- **Hiện trạng:** LLM chỉ nhận `supplier_id` (UUID) nên `rationale` in thẳng UUID.
- **Yêu cầu (CẦN DUYỆT vì đổi payload gửi LLM, tức đổi prompt/ngữ cảnh):** thêm ánh xạ `supplier_id → supplier_name` vào user message của `decision_llm`, dặn model dùng tên trong lời giải trình nhưng **vẫn trả `supplier_id` nguyên văn** ở các trường ID. Validate sau LLM không đổi. Chạy lại eval trước/sau và ghi số liệu.
- **Test:** stub LLM kiểm tra user payload có chứa tên NCC và `allowed_supplier_ids` không đổi.

### D2. Chuẩn hóa kiểu ở `intake.py`
- Import đúng model dùng thật ở route (hoặc đổi cả hai cùng lúc), tránh annotation `QuotationConfirmation` bản mới trong khi runtime nhận bản cũ. Không đổi hành vi. Test: `confirm` agent-mode với payload có `shipping_fee` vẫn thành công.

---

## Thứ tự đề xuất
1. A1 → A2 → A3 (chặn lỗi chạy thật)
2. B1 → B2 → B3 → B4 (đưa bộ test về xanh, có kiểm soát)
3. Chốt C1–C4 với chủ dự án, rồi mới làm C và D.

## Tiêu chí hoàn thành
- `pytest tests/ -q` không còn lỗi collection; mọi lỗi còn lại (nếu có) được liệt kê có lý do.
- Nạp lại `data/procurement-workflow.sqlite` hiện có: mọi run qua `public_run` + `ProcurementAnalysis.model_validate` đều hợp lệ.
- Không có test bị xóa/skip/nới assert ngoài các mục đã được duyệt rõ (B1).
- Đáp án `calculate_tco`/`compare_suppliers` không đổi, trừ khi C1-P2 hoặc C3(b) được duyệt.

## Rủi ro và giả định
- Giả định `data/*.json` và `.sqlite` đang dùng là dữ liệu dev; mọi migration phải không xóa payload audit.
- A1 và B2 đụng cùng `workflow.py`/test tích hợp; nên làm tuần tự để tránh xung đột.
- Chưa chạy được `pytest`/FastAPI trong lần rà soát này nên danh sách test lỗi là suy ra từ đọc code và `.pytest_cache/lastfailed`; Codex cần chạy thật để xác nhận từng mục.
