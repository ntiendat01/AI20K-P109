# Chạy luồng FE – BE – Agent

Trạng thái: **In Review**. Happy path đã chạy ở API và trình duyệt với extraction/decision model giả, graph/evaluation/Chroma/repository thật. Lượt dùng OpenAI thật cần API key trên máy.

## Khởi động

Chạy từ thư mục gốc dự án:

```sh
.venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000/ui/`. FE gọi `/api/v1` cùng origin; BE gọi LangGraph trong tiến trình và cấp evaluation dependencies ở lifespan. Không cần một agent server riêng.

Sau khi thư mục cha đổi từ `AI Thuc Chien` thành `AI_Thuc_Chien`, một số console script trong `.venv/bin` còn shebang cũ. Lệnh `python -m ...` ở trên chạy được tại đường dẫn mới. Không chỉnh `.env` hoặc cài lại dependency trong lần tích hợp này.

## Provider

Luồng extraction và decision dùng cùng OpenAI API key với `gpt-6-luna`. Trong
`.env`, đặt `LLM_PROVIDER=openai`, `MODEL_NAME=gpt-6-luna`, rồi điền
`OPENAI_API_KEY`; khởi động lại BE sau khi lưu. Không gửi key vào chat hoặc
commit key.

| Thành phần              | Biến cấu hình                                                    |
| ----------------------- | ---------------------------------------------------------------- |
| OpenAI GPT-6 Luna       | `OPENAI_API_KEY`, `LLM_PROVIDER=openai`, `MODEL_NAME=gpt-6-luna` |
| JSON/độ trễ             | `OPENAI_REASONING_EFFORT=none`, `OPENAI_TIMEOUT_SECONDS=120`     |
| PDF scan cần OCR hosted | `PADDLEOCR_BASE_URL`, `PADDLEOCR_ACCESS_TOKEN`                   |

PDF có text đọc bằng PyMuPDF; PDF scan chuyển sang PaddleOCR hosted. Model phải trả JSON theo contract; lỗi schema/evidence không được chuyển sang approval.

## Happy path trên UI

1. Đăng nhập Buyer: `purchasing@vinuni.edu.vn` / `Purchase123!` (hoặc nút tài khoản demo).
2. Tạo PR cho một mặt hàng, số lượng chung, ngân sách VND và hạn giao.
3. Upload ít nhất hai báo giá từ NCC khác nhau. Chọn **Đọc và trích xuất bằng AI (PDF)** để dùng `extract_documents`; chọn parser để kiểm Mốc A trước.
4. Đối chiếu file gốc. Xác nhận tên/mã hàng, UOM, số lượng, giá, VAT, phí, số ngày lịch sau xác nhận đơn và tháng bảo hành. Nút xác nhận đồng thời xác nhận tổng tiền gồm VAT hiển thị trên form.
5. Mở comparison và bấm **Phân tích bằng Agent**. BE lập snapshot, ingest evidence, chạy `normalize → decision_llm → evaluate`. Chỉ trạng thái `awaiting_review` mới gửi duyệt được.
6. Bấm **Gửi Quản lý phê duyệt**. Đăng xuất rồi đăng nhập Manager: `manager@vinuni.edu.vn` / `Manager123!`.
7. Mở PR chờ duyệt, xem xếp hạng, số liệu, bằng chứng, đánh đổi và uncertainty. Bấm **Phê duyệt và tạo PO nháp**.
8. Mở PO; tiền hàng, VAT bổ sung, phí và tổng phải khớp dữ liệu đã duyệt. Refresh đọc lại PO đã lưu. Retry cùng feedback không sinh PO thứ hai.

Ca tính tay đã kiểm: Widget × 10; A giá 1.000, VAT 10%, phí 0, giao 5 ngày, bảo hành 12 tháng → **11.000 VND**; B giá 1.200, VAT 10%, phí 0, giao 7 ngày, bảo hành 24 tháng → **13.200 VND**. PR ngân sách 20.000 VND, hạn sau 30 ngày. Fixture quyết định chọn A; provider thật có thể chọn NCC khác nếu đề xuất đó qua đầy đủ evaluation.

## API và kho dùng chung

| API                                          | Vai trò / ý nghĩa                                              |
| -------------------------------------------- | -------------------------------------------------------------- |
| `POST /api/v1/prs/{id}/quotations`           | Buyer upload; form `extraction_mode=agent` hoặc `parser`       |
| `POST /api/v1/quotations/{id}/confirm`       | Buyer corrections + audit; AI intake được resume rõ ràng       |
| `POST /api/v1/quotations/{id}/reopen`        | Buyer sửa lại trước khi gửi duyệt; snapshot cũ hết hiệu lực    |
| `POST/GET /api/v1/prs/{id}/analysis`         | Chạy / đọc analysis bền vững của cùng PR                       |
| `GET /api/v1/recommendations/{id}/review`    | Renderer chỉ xuất factual claims đã kiểm chứng                 |
| `POST /api/v1/prs/{id}/submit-approval`      | Gửi đúng analysis đã qua evaluation                            |
| `POST /api/v1/recommendations/{id}/feedback` | Manager approve/reject/revise với ID, version, idempotency key |
| `GET /api/v1/pos/{id}`                       | PO nháp đã lưu                                                 |

PR/quotation/PO giữ repository JSON hiện có. Analysis/snapshot/finalization dùng `PROCUREMENT_WORKFLOW_PATH`; EvaluationStore dùng `EVALUATION_DATABASE_PATH`; evidence dùng `CHROMA_PERSIST_DIR`. Tenant do `PROCUREMENT_TENANT_ID` phía server quản lý. Supplier UUID do repository cấp khi Buyer xác nhận; body không được cấp quyền/ID authoritative. Demo dùng tên chuẩn hóa để tìm alias NCC, chưa có supplier master hoặc mã số thuế để xác minh thực thể pháp lý.

Snapshot giữ PR requirements, quotation IDs/supplier IDs, file hash, human edits và policy/date. Số liệu Buyer xác nhận là evidence `human_edit`, có actor/time/before/after và liên kết nguồn; không coi kết luận LLM là tài liệu nguồn. TCO replay dùng goods/fee tax-inclusive đã được Buyer xác nhận. Không đoán VAT/phí bằng 0 khi thiếu.

Pending intake và text OCR gốc (ẩn khỏi JSON công khai) được lưu trong quotation. Sau restart, BE dựng lại đúng ranh giới review từ dữ liệu đã lưu rồi `Command(resume=...)`; không OCR/LLM lại. Review sau evaluation lưu SQLite. Approval command được ghi trước receipt; startup reconcile hoàn tất PO/PR nếu lỗi xảy ra sau khi receipt đã approved. Session demo vẫn ở RAM nên cần đăng nhập lại sau restart.

## Lỗi và review lại

- `needs_input`: bổ sung dữ liệu; dùng **Sửa dữ liệu và phân tích lại** cho quote đã khóa trước khi gửi duyệt.
- `technical_failure`: kiểm tra provider/kho bằng chứng rồi thử lại. `repairable`: xem diagnostics, chạy lại; chưa bật auto-repair.
- `exception_required` / `no_viable_supplier`: không có approval/PO tự động; cần xử lý điều kiện đầu vào hoặc quy tắc bởi owner.
- Reject: PR về comparing, recommendation cũ terminal; phân tích lại tạo ID mới.
- **Yêu cầu giải thích lại**: receipt ở `received`, PR về comparing; Buyer chạy lại với cùng recommendation ID và version mới. Chỉ `mark_feedback_applied()` khi version mới đã evaluation đầy đủ và chờ review.
- Data/preference/rule revisions được route tới owner và giữ `awaiting_input`; editor/quyền owner cho các loại này chưa tích hợp đầy đủ. Không báo chúng là applied và không tạo PO.
- `/api/prs` là API debug cũ với case RAM; các endpoint analysis/pipeline đã deprecated và không auto-confirm extraction. FE dùng `/api/v1` làm luồng nghiệp vụ chính.

Phạm vi demo: một mặt hàng, cùng quantity/UOM và VND, ≥2 NCC, explicit VAT/phí/lead time/warranty. Embedding cục bộ dùng token hashing để truy hồi; verifier kiểm exact facts/hash/scope. Không có job queue, multi-worker transaction hoặc identity production trong mốc này.

## Kiểm thử và live smoke

```sh
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src/ tests/
.venv/bin/python -m scripts.evaluate_post_decision --output /private/tmp/p109-evaluation.json
```

Khi cấu hình OpenAI thật, chạy smoke trên dữ liệu PDF ẩn danh, business/evidence stores tạm và simulated Buyer/Manager. Script không inject provider giả; nó gọi extraction và decision model đã cấu hình, kiểm TCO, evaluation, PO và retry:

```sh
.venv/bin/python -m scripts.smoke_procurement_live --provider openai --output /private/tmp/procura-live-openai.json
```

Không gọi script live từ pytest. Kết quả `not_ready` không được coi là pass. Sau smoke API thật, thao tác lại toàn luồng UI với cùng provider để xác nhận latency, extraction và trạng thái thực tế.

Kết quả đã đo và trace: [báo cáo tích hợp](end-to-end-integration-results.md).
