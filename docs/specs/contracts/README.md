# Procurement Contracts — Draft for Review

Status: **DRAFT — chưa dùng để migration hoặc thay đổi API runtime**.

Thư mục này định nghĩa contract mục tiêu trước khi refactor schema. Khi có xung đột với code hiện tại, contract này mô tả thiết kế đề xuất, không khẳng định code đã triển khai.

## Tài liệu

- [domain-and-storage.md](domain-and-storage.md): aggregate, entity, revision và bảng lưu trữ.
- [pipeline.md](pipeline.md): artifact và input/output của từng component.
- [api.md](api.md): HTTP commands, jobs và resource responses.

## Quyết định đã chốt

1. Buyer xác nhận extraction trước khi normalize.
2. Normalize là deterministic tool, không phải một HITL checkpoint riêng.
3. Không thể normalize thì trả lỗi/flag rõ ràng; không gắn nhãn giá trị gốc là giá trị đã normalize.
4. `calculate_tco` và `analyze_risks` có thể chạy song song.
5. `compare_suppliers` phụ thuộc `tco_results`, nên chạy sau TCO.
6. Decision LLM chỉ tổng hợp các artifact đã tính; không tự tính lại TCO hoặc tự tạo facts.
7. FastAPI chỉ xử lý HTTP boundary và gọi application service; không điều phối node trực tiếp.
8. LangGraph điều phối workflow; domain rules, TCO, normalization và PO issuance nằm trong deterministic services.
9. Relational database là system of record. Vector store là derived index có thể tái tạo.
10. Original document và confirmed revisions là immutable.

## Invariants bắt buộc

- Mỗi command thay đổi state phải có `actor_id`, `tenant_id` và `correlation_id`.
- Mỗi artifact phải có `schema_version` và tham chiếu input revision.
- Chỉ quotation revision `confirmed` mới được đưa vào analysis.
- Analysis luôn chạy trên immutable snapshot; không đọc quotation “latest” trong lúc đang chạy.
- Quotation revision mới làm analysis cũ thành `superseded`.
- Approval phải tham chiếu đúng `analysis_id` và `analysis_revision`.
- AI recommendation bắt buộc qua Buyer review/submit trước khi Manager có thể approve/revise/reject.
- Chỉ analysis `pending_manager_approval` có Buyer confirmation hợp lệ mới được Manager quyết định.
- Một approval command chỉ sinh tối đa một PO (`idempotency_key`).
- PO không được lấy số liệu trực tiếp từ Decision LLM.
- Raw extraction, human correction, normalized value và evidence không được ghi đè lẫn nhau.

## Ngoài phạm vi vòng refactor đầu

- OCR handwriting và phục hồi bảng phức tạp nhiều trang.
- FX provider thời gian thực.
- Supplier quality profile/RAG policy scoring.
- Evaluator/grounding không thuộc pipeline hiện tại; Decision Proposal đi thẳng tới Buyer HITL.
- Distributed queue và multi-region deployment.

Các mục trên có thể thêm sau nhưng contract hiện tại không được ngăn cản việc mở rộng.

## Open decisions cần phản biện

1. MVP dùng SQLite chung hay chuyển ngay PostgreSQL?
2. Analysis API trả `202 + job_id` ngay trong MVP hay giữ sync tạm thời sau application-service boundary?
3. UOM/FX rule do code/config quản lý hay lưu thành versioned database records?
4. Cho phép Buyer confirm khi còn field bắt buộc thiếu hay bắt buộc sửa đủ trước?
5. Decision LLM được quyền đổi thứ hạng deterministic hay chỉ giải thích? Đề xuất mặc định: chỉ giải thích; khác ranking phải tạo exception.
6. Shipping cost lấy từ báo giá, logistics rule, Finance hay chỉ tính cho shortlist? Trong lúc chờ xác nhận nghiệp vụ, shipping cost không phải input bắt buộc và không được mặc định bằng `0`.
