# Bước 2 — Tải file báo giá và nhận trích xuất sơ bộ

**Input:** `pr_id`, các file báo giá. **UI wizard:** chỉ nhận PDF, tối đa 5 file mỗi PR, mỗi file ≤5 MB; upload từng file qua `POST /api/v1/prs/{pr_id}/quotations` (`multipart/form-data`). Endpoint còn nhận `supplier_name?`, `extraction_mode?` (`parser`/`agent`), `extraction_job_id?`. API cho phép PDF/TXT/EML, tối đa 10 báo giá/PR, mỗi file ≤5 MB. PR phải ở `awaiting_quotation` hoặc `comparing`.

## Hợp đồng dữ liệu tại ranh giới

| Dữ liệu | Kiểu / ý nghĩa | Nơi sinh / sử dụng |
| --- | --- | --- |
| `file` | bytes và filename, PDF/TXT/EML theo API | Buyer gửi; parser đọc trực tiếp, agent chỉ nhận PDF |
| `source_hash` | SHA-256 của bytes | Server; nhận diện file và cache extraction parser |
| `source_filename`, `source_content_type`, `source_path` | metadata file; `source_path` nội bộ | Object storage filesystem/S3; `source_path` không trả công khai |
| `supplier_name` | form tùy chọn | Ưu tiên tên Buyer nhập → tên trích xuất → filename |
| `extraction_mode` | `parser` hoặc `agent` | Mặc định lấy config; agent dùng OCR/extraction pipeline |
| `extraction_job_id` | string tùy chọn | UI theo dõi/hủy tiến trình upload agent |

**Output `Quotation` chưa xác nhận** (`201`):

```json
{
  "id": "<uuid>", "pr_id": "<pr-id>", "supplier_id": null,
  "supplier_name": "NCC A", "source_filename": "bao-gia.pdf",
  "source_hash": "<sha256>", "source_content_type": "application/pdf",
  "extraction_version": 1, "status": "unconfirmed",
  "currency": "VND", "delivery_time": "", "payment_terms": "", "warranty": "",
  "items": [], "extraction_warnings": [], "cache_hit": false,
  "vat_rate": null, "vat_included": null, "shipping_fee": null,
  "lead_time_days": null, "warranty_months": null, "confirmed_at": null
}
```

`items[]` sơ bộ gồm `product_name`, `product_code`, `unit`, `quantity`, `unit_price`, `line_total`, `matched_pr_item_id?`, `match_status?`. Parser và agent có thể điền giá trị khác nhau; các trường thương mại còn `null` đến khi Buyer xác nhận. `agent_extractions[]` giữ evidence trích xuất; `source_ocr_text` và `confirmation_audit` lưu nội bộ.

## Xử lý và persistence

```mermaid
sequenceDiagram
  actor Buyer
  participant UI
  participant API
  participant Extract as Parser / Agent OCR
  participant Store as Quotation repository + object storage
  Buyer->>UI: Chọn PDF
  UI->>API: multipart file, extraction_mode, job_id
  API->>API: Kiểm tra PR, format, số file, kích thước; SHA-256
  API->>Extract: Đọc nội dung / cache parser
  Extract-->>API: ExtractedQuotation
  API->>Store: Lưu file + Quotation unconfirmed
  Store-->>UI: Quotation sơ bộ
```

`GET /api/v1/prs/{id}/quotations` liệt kê báo giá; `POST /api/v1/quotations/{id}/re-extract` chạy lại cho báo giá chưa xác nhận; `POST /api/v1/prs/{id}/quotations/cancel` hủy job; `DELETE /api/v1/quotations/{id}` xóa file/record trước duyệt. Việc upload **chưa tăng** `PR.quotation_count`; con số này đếm báo giá đã xác nhận ở B3.

**Điểm cần rà soát:** giới hạn 5 của UI so với 10 của API; bộ cache parser keyed theo hash + extraction version; nếu muốn truy nguyên kết quả OCR cần xem `agent_extractions` và nguồn nội bộ, không chỉ response public.

Nguồn: [`procurementWorkflow.tsx`](../../frontend/src/features/procurementWorkflow.tsx), [`procurement.py`](../../src/api/routes/procurement.py), [`quotation/repository.py`](../../src/infrastructure/quotation/repository.py), [`confirmation.py`](../../src/domain/quotation/confirmation.py).
