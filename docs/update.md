# Kế hoạch Nâng cấp Kiến trúc & Khắc phục Điểm yếu Decision LLM

> **Mục đích tài liệu:** Lưu trữ chi tiết các điểm yếu, rủi ro tiềm ẩn trong thiết kế hiện tại và cung cấp lộ trình / hướng dẫn kỹ thuật cụ thể để nâng cấp hệ thống khi chuyển từ giai đoạn MVP sang Production quy mô lớn mà **không làm vỡ kiến trúc cốt lõi**.

---

## I. TỔNG QUAN KIẾN TRÚC HIỆN TẠI

Kiến trúc hiện tại tuân thủ nguyên tắc **Separation of Concerns** và **Contract-First**:
* **Deterministic Tools:** Tính toán TCO, thời gian giao hàng, bảo hành và ma trận so sánh đối đầu bằng công thức toán học tuyệt đối (Python Decimal), không để LLM làm toán.
* **Decision LLM:** Đóng vai trò là "Chuyên viên Tổng hợp & Lập luận" (Synthesizer & Reasoner), tiếp nhận kết quả đã tính toán và PR constraints để viết ra bản đề xuất (`DecisionProposal`).
* **Human-in-the-Loop (HITL):** Hai chốt chặn bắt buộc gồm HITL-1 (Buyer đối soát bóc tách) và HITL-2 (Manager phê duyệt đề xuất phát hành PO).

---

## II. DANH SÁCH ĐIỂM YẾU & RỦI RO TIỀM ẨN

### 1. Tính ngẫu nhiên & Thiếu nhất quán (Non-deterministic Reasoning)
* **Vấn đề:** Dù thiết lập `temperature = 0.0`, LLM vẫn có thể đưa ra thứ hạng khác nhau giữa 2 lần chạy nếu các nhà cung cấp có ưu/nhược điểm ngang ngửa (ví dụ: NCC A rẻ hơn 2% nhưng NCC B giao hàng sớm hơn 2 ngày).
* **Rủi ro:** Gây bối rối cho Buyer/Manager và khó giải trình khi kiểm toán nội bộ.
* **Giải pháp nâng cấp sau này:**
  * Bổ sung bảng **Trọng số tiêu chí (MCDA - Multi-Criteria Decision Analysis)** vào cấu hình PR (ví dụ: Giá chiếm 60%, Lead time 30%, Bảo hành 10%).
  * Hệ thống deterministic sẽ chấm điểm tổng hợp (Total Score) trước, sau đó LLM chỉ giải trình dựa trên điểm số đã chốt.

---

### 2. Ảo giác định tính trong Lời giải trình (Qualitative Hallucinations)
* **Vấn đề:** Mặc dù LLM không thể bịa ra con số TCO mới, nó vẫn có thể tự chèn các nhận định định tính không có trong báo giá gốc vào phần `rationale` (ví dụ: *"NCC A là thương hiệu lâu đời, uy tín hàng đầu"* — trong khi PDF không hề đề cập).
* **Rủi ro:** Đưa thông tin thiếu căn cứ vào báo cáo trình duyệt.
* **Giải pháp nâng cấp sau này:**
  * Kích hoạt đầy đủ tầng **Grounding & Evidence Evaluator** (`src/services/evaluation/grounding.py`).
  * Mọi khẳng định trong `rationale` đều phải ánh xạ ngược về ít nhất một `SourceFact` hợp lệ từ file PDF gốc, nếu không sẽ bị gán nhãn `CONTRADICTED_CLAIM` hoặc `UNSUPPORTED_OPTIONAL_CLAIM`.

---

### 3. Mô hình "Một người chiến thắng" (Single Winner vs. Split PO)
* **Vấn đề:** Schema hiện tại chỉ trả về 1 `preferred_supplier_id` duy nhất cho toàn bộ PR.
* **Rủi ro:** Với các PR có nhiều mặt hàng (Multi-item / Multi-SKU), việc mua toàn bộ từ 1 NCC có thể làm tăng chi phí tổng thể (ví dụ: NCC A bán Laptop rẻ nhất, nhưng NCC B bán Máy in rẻ nhất).
* **Giải pháp nâng cấp sau này:**
  * Mở rộng schema `DecisionProposal` bằng cách thêm trường tùy chọn (Optional Field) `item_allocations`:
    ```json
    {
      "preferred_supplier_id": "supplier-a",
      "item_allocations": [
        {"item_id": "laptop-01", "supplier_id": "supplier-a"},
        {"item_id": "printer-02", "supplier_id": "supplier-b"}
      ]
    }
    ```
  * PO Service sẽ phát hành 2 đơn đặt hàng (Split POs) tương ứng cho từng NCC.

---

### 4. Xử lý vi phạm nhẹ tiêu chí PR (Tolerance Policy)
* **Vấn đề:** Nếu tất cả các báo giá đều vượt nhẹ ngân sách (ví dụ: Budget 100tr, các báo giá là 102tr, 105tr, 110tr), LLM có thể lúng túng giữa việc từ chối (`needs_input`) hay tự ý "châm chước" chọn NCC 102tr.
* **Rủi ro:** Hệ thống xử lý cảm tính hoặc dễ bị tắc luồng (Deadlock).
* **Giải pháp nâng cấp sau này:**
  * Bổ sung chính sách biên độ dung sai vào `src/core/config.py`:
    * `BUDGET_TOLERANCE_PERCENT = 0.05` (Cho phép vượt tối đa 5% kèm cảnh báo).
    * `LEAD_TIME_TOLERANCE_DAYS = 2` (Cho phép trễ tối đa 2 ngày kèm cảnh báo).

---

### 5. Tải ngữ cảnh & Hiện tượng "Lost in the Middle" khi số lượng NCC lớn
* **Vấn đề:** Khi có 10–20 NCC tham gia chào giá, mỗi bên có nhiều mặt hàng, kích thước prompt gửi vào LLM sẽ rất lớn.
* **Rủi ro:** Tăng độ trễ, tốn nhiều chi phí token, và LLM có xu hướng bỏ quên các NCC nằm ở giữa prompt.
* **Giải pháp nâng cấp sau này:**
  * Áp dụng thuật toán **Hard Filtering / Pre-ranking** ở tầng Python để lọc ra Top-3 hoặc Top-5 ứng viên tiềm năng nhất trước khi nạp vào Decision LLM.

---

### 6. Giới hạn vòng lặp sửa lỗi tự động (Repair Loop Bounding)
* **Vấn đề:** Khi Evaluator phát hiện lỗi trong đề xuất, LLM được gọi lại qua `DecisionOutputRepair` để sửa. Quá trình này có thể lặp lại nhiều lần nếu LLM liên tục sinh lỗi mới.
* **Giải pháp:**
  * Giữ giới hạn cứng: Tối đa 2 lần auto-repair (`auto_repairs <= 2`).
  * Nếu sau 2 lần vẫn không đạt, đánh dấu `untrusted_proposal` và chuyển thẳng lên màn hình duyệt của Buyer/Manager.

---

## III. CÁC HẠNG MỤC NÂNG CẤP HẠ TẦNG & PIPELINE

| Hạng mục | Thực trạng MVP | Nâng cấp Production | Cách triển khai không phá vỡ kiến trúc |
| :--- | :--- | :--- | :--- |
| **Trích xuất PDF** | Dùng 1 luồng OCR chính | Bổ sung nhánh **PyMuPDF Native Text Extractor** | Thêm class `NativePdfExtractor`, bypass OCR khi phát hiện Native PDF để tăng tốc gấp 50 lần. |
| **Hủy tác vụ (Cancel)** | Không có nút hủy job | Thêm `POST /jobs/{id}/cancel` | Gửi tín hiệu ngắt (Cancellation Token) tới background task LangGraph. |
| **Giao tiếp Real-time** | HTTP Polling 1s/lần | Hỗ trợ **Server-Sent Events (SSE)** | Thêm endpoint `GET /jobs/{id}/events` stream trực tiếp tiến độ về UI. |
| **Phân trang & Lọc** | Trả toàn bộ danh sách | Hỗ trợ `page`, `limit`, `status` | Bổ sung query params vào các endpoint `GET /prs`, `GET /quotations`. |

---

## IV. KẾT LUẬN & NGUYÊN TẮC THỰC THI

* **Nguyên tắc hiện tại:** Tập trung chạy thật mượt mà, chính xác và ổn định luồng **MVP Happy Path** (Upload $\rightarrow$ Bóc tách $\rightarrow$ Buyer Review $\rightarrow$ Phân tích & Đề xuất 1 NCC $\rightarrow$ Duyệt PO).
* **Đảm bảo tính mở rộng:** Mọi nâng cấp trong tài liệu này đều được thiết kế dưới dạng **Non-breaking Additions** (thêm node mới, thêm config, thêm optional field), hoàn toàn không cần viết lại hệ thống cốt lõi.

---

## V. BACKLOG CÁC PHẦN CHƯA CHỐT SAU KHI XÁC NHẬN CONTRACT

Phần này là nguồn theo dõi chính cho những quyết định chưa đưa vào schema/runtime vòng refactor đầu. Các mục ở đây không được triển khai ngầm bằng giá trị mặc định làm sai nghĩa nghiệp vụ.

### A. Quyết định nghiệp vụ chưa chốt

| ID | Chủ đề | Mặc định an toàn hiện tại | Cần xác nhận sau |
|---|---|---|---|
| BIZ-01 | Shipping cost | Không thuộc confirmed quotation; `shipping_amount = null`, không đổi thành `0` | Nguồn phí ship là báo giá, Logistics hay Finance; tính cho toàn bộ NCC hay chỉ shortlist; VAT của shipping xử lý thế nào |
| BIZ-02 | Buyer thêm item ngoài extraction | Vòng đầu yêu cầu `source_item_id` thuộc extraction draft | Có cho phép thêm dòng mới; cách đánh dấu `human_added`; provenance và validation cho dòng mới |
| BIZ-03 | Field bắt buộc bị thiếu | Structural issue có thể chặn confirm | Danh sách field bắt buộc theo loại PR/báo giá; Buyer có quyền override hay phải bổ sung đủ |
| BIZ-04 | Thẩm quyền xếp hạng | Deterministic tools tạo facts/matrix; LLM tổng hợp đề xuất | LLM được tự đổi thứ hạng hay chỉ giải thích ranking deterministic; khi đổi có cần exception/override reason |
| BIZ-05 | Manager chọn khác đề xuất | Chỉ yêu cầu supplier thuộc analysis snapshot | Có bắt buộc `override_reason`; supplier nào bị coi là ineligible; quyền override theo vai trò |
| BIZ-06 | Revise workflow | Chưa chuẩn hóa đầy đủ routing | Phân biệt sửa dữ liệu, ưu tiên, policy hay explanation; mỗi loại quay lại node/owner nào |
| BIZ-07 | Tolerance policy | Không tự châm chước budget/deadline | Ngưỡng vượt ngân sách, trễ deadline, warranty tối thiểu và quyền phê duyệt ngoại lệ |
| BIZ-08 | Một hay nhiều NCC cho một PR | MVP chọn một supplier và tạo một PO | Có hỗ trợ split award/item allocation và nhiều PO cho PR nhiều SKU hay không |
| BIZ-09 | Supplier quality | Chưa dùng quality score/RAG làm tiêu chí chính thức | Nguồn dữ liệu, owner, chu kỳ cập nhật và cách chấm điểm chất lượng NCC |

### B. Quyết định dữ liệu và schema chưa chốt

| ID | Chủ đề | Mặc định an toàn hiện tại | Cần xác nhận sau |
|---|---|---|---|
| DATA-01 | Database engine | Thiết kế relational, chưa khóa SQLite hay PostgreSQL | MVP dùng một SQLite chung hay chuyển ngay PostgreSQL; concurrency và deployment target |
| DATA-02 | UOM rules | Deterministic, versioned bằng `rule_version`; không map được thì `null/needs_mapping` | Rule nằm trong code/config hay bảng DB; ai có quyền cập nhật mapping |
| DATA-03 | FX rates | Chỉ dùng rate/rule đã cấu hình; không đoán | Static config hay provider thời gian thực; nguồn, timestamp, rate type và fallback policy |
| DATA-04 | Global confidence threshold | Một global config, mặc định `0.80`, snapshot vào extraction | Có UI/admin config hay chỉ environment; thay threshold có revalidate extraction cũ không |
| DATA-05 | Evidence/vector schema | Deferred khi evaluator tắt; vector store chỉ là derived index | Khi bật evaluator, metadata/citation granularity và retention/index rebuild policy |
| DATA-06 | Data retention | Chưa chốt thời hạn | Retention cho PDF, OCR blocks, raw extraction, revisions, jobs, prompts và provider responses |
| DATA-07 | Deduplication | Có `content_hash`, không ghi đè file | Trùng file trong cùng PR/tenant xử lý reuse, reject hay tạo quotation mới |
| DATA-08 | Decimal precision | API dùng decimal string | Precision/scale theo currency, rounding mode và reconciliation tolerance chính thức |

### C. Pipeline và AI deferred

| ID | Chủ đề | Mặc định an toàn hiện tại | Nâng cấp sau |
|---|---|---|---|
| AI-01 | Evaluator/grounding | Loại khỏi pipeline; `DecisionProposal` đi thẳng tới Buyer HITL | Chỉ xem xét lại như một initiative riêng nếu có requirement mới |
| AI-02 | Auto-repair | Không dùng trong pipeline hiện tại | Buyer yêu cầu revise sẽ tạo analysis/recommendation revision mới |
| AI-03 | Prompt context lớn | Gửi structured outputs của các tool | Pre-filter/shortlist khi có nhiều NCC hoặc nhiều SKU; tránh lost-in-the-middle |
| AI-04 | OCR handwriting | Ngoài phạm vi MVP | Engine/fallback và confidence policy cho chữ viết tay |
| AI-05 | Bảng nhiều trang/phức tạp | Ngoài phạm vi happy path | Table reconstruction và provenance xuyên trang |
| AI-06 | Native PDF optimization | Pipeline hiện dùng một OCR extractor boundary | Có bypass bằng PyMuPDF khi PDF có text hay vẫn dùng một engine thống nhất |
| AI-07 | Provider fallback | Chưa chốt ma trận fallback | Provider priority, timeout, retry, schema compatibility và cost limits |

### D. API và vận hành chưa chốt

| ID | Chủ đề | Mặc định an toàn hiện tại | Cần bổ sung sau |
|---|---|---|---|
| OPS-01 | Job runner | Contract đã dùng `202 + job_id`; implementation chưa chọn | In-process queue, worker riêng hay Redis/Celery/RQ; restart/resume semantics |
| OPS-02 | Idempotency semantics | Các command quan trọng nhận `Idempotency-Key` | Scope key, retention, payload hash mismatch, replay status code và concurrent duplicate behavior |
| OPS-03 | Timeout/retry | Đặt tại adapter boundary | Timeout từng OCR/LLM provider, max attempts, backoff, circuit breaker và retryable errors |
| OPS-04 | Cancel/retry endpoint | Chưa có trong MVP contract | `POST /jobs/{id}/cancel`, `/retry`, quyền gọi và trạng thái chuyển tiếp |
| OPS-05 | Realtime progress | Polling `GET /jobs/{id}` | SSE/WebSocket, event retention và reconnect cursor |
| OPS-06 | Job progress | Có field `progress` nhưng chưa chốt cách tính | Percentage hay completed-steps/total-steps; xử lý bước có thời lượng không xác định |
| OPS-07 | Authentication | Có role Buyer/Manager nhưng cơ chế production chưa chốt | JWT/session, expiry/refresh, object-level authorization và tenant isolation |
| OPS-08 | Rate limit/quota | Chưa có contract | Giới hạn file, page, concurrent job, OCR/LLM budget theo tenant/user |
| OPS-09 | Error taxonomy | Có error envelope cơ bản | Danh mục error code đầy đủ, mapping HTTP status và retryability |
| OPS-10 | Distributed deployment | Ngoài phạm vi MVP | Multi-worker locking, shared storage, distributed checkpoint và multi-region |

### E. Migration và compatibility chưa chốt

| ID | Chủ đề | Mặc định an toàn hiện tại | Cần thực hiện sau |
|---|---|---|---|
| MIG-01 | JSON/SQLite cũ sang schema mới | Không xóa kho cũ trong release migration đầu | Mapping, backfill revision/version, script kiểm đếm và rollback |
| MIG-02 | Legacy synchronous analysis API | Giữ facade tạm thời | Thời hạn deprecation, mapping response và thứ tự migrate frontend |
| MIG-03 | Dual read/write | Chưa bật | Có cần dual-write hay chỉ one-time migration; cách phát hiện divergence |
| MIG-04 | Existing Chroma data | Coi là derived/disposable | Rebuild collection từ document/provenance sau cutover |
| MIG-05 | Existing confirmed quotations | Dữ liệu cũ chưa có immutable revision đầy đủ | Quy tắc tạo revision đầu tiên, actor/timestamp fallback và audit marker `migrated` |

## VI. NGUYÊN TẮC QUẢN LÝ BACKLOG

- Mỗi mục chỉ được chuyển vào contract chính sau khi có quyết định nghiệp vụ hoặc kỹ thuật rõ ràng.
- Khi chốt một mục, cập nhật đồng thời `specs/contracts/api.md`, `pipeline.md` và `domain-and-storage.md` nếu có ảnh hưởng chéo.
- Không dùng `0`, chuỗi rỗng hoặc giá trị giả để thay cho dữ liệu chưa chốt; dùng `null`, trạng thái `needs_input` hoặc issue có mã rõ ràng.
- Thay đổi làm ảnh hưởng dữ liệu cũ phải kèm migration, kiểm đếm và rollback plan.
- Các mục deferred không được âm thầm xuất hiện trong happy path MVP.
