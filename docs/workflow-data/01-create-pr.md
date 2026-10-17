# Bước 1 — Khai báo nhu cầu và tạo PR

**Actor:** Buyer (`procurement`). **UI:** `/purchase-requests/new`; sau khi tạo, `/purchase-requests/{id}/workflow/1` cho phép chỉnh sửa. **API:** `POST /api/v1/prs` (201), tùy chọn `?is_draft=true`; đọc lại qua `GET /api/v1/prs/{id}`.

## Input

| Trường `PurchaseRequestCreate` | Kiểu / ràng buộc backend | Nguồn UI / ý nghĩa |
| --- | --- | --- |
| `code` | string, 3–50, `^[A-Za-z0-9_-]+$` | Mã PR, UI tự gợi ý; repository trim và uppercase, kiểm tra trùng không phân biệt hoa thường |
| `category` | string, 3–500 | Tên PR |
| `requested_quantity` | Decimal `> 0` | UI cộng `items[].quantity` |
| `requested_uom` | string không rỗng | UI lấy đơn vị dòng đầu tiên; không đại diện đủ nếu danh mục có nhiều UOM |
| `target_currency` | string không rỗng | UI chọn VND/USD |
| `estimated_budget` | Decimal `>= 0`, tối đa 18 chữ số, 2 số lẻ | Ngân sách dự kiến; UI nhập số |
| `delivery_due_date` | ISO date | Hạn nhận hàng; UI yêu cầu từ ngày mai, backend không ràng buộc tương lai |
| `metadata` | object tùy chọn | UI gửi `requested_by`, `purpose`; model còn `budget`, `delivery_time`, `department` |
| `items[]` | `PRItem[]`, mặc định `[]` | UI yêu cầu ít nhất 1; mỗi dòng: `order_index`, `product_name`, `quantity > 0`, `unit`, `notes?`, `item_id?` |

Payload ví dụ (số Decimal có thể đến API dạng JSON number, response domain serialize dạng string):

```json
{
  "code": "PR-20261015-0001",
  "category": "Mua vật liệu xây dựng",
  "requested_quantity": 15,
  "requested_uom": "Cái",
  "target_currency": "VND",
  "estimated_budget": 16000000,
  "delivery_due_date": "2026-10-30",
  "metadata": {"requested_by": "Buyer A", "purpose": "Bổ sung vật tư"},
  "items": [{"order_index": 0, "product_name": "Vật tư A", "quantity": 15, "unit": "Cái", "notes": ""}]
}
```

CSV là **đường nhập phụ trước khi tạo PR**: `POST /api/v1/prs/extract-items` multipart `file=.csv`, UTF-8, cột `Tên sản phẩm`, `Số lượng`, `Đơn vị`, `Ghi chú`. Output `{valid_items: [...], errors?: [{row, column, message}]}` chỉ đổ vào form; không tự lưu PR. Route hiện không gắn `require_role`, còn route tạo PR thì có.

## Output và lưu trữ

`PurchaseRequest` trả về gồm `id`, `tenant_id`, `code`, `creator_id`, `creator_name`, toàn bộ trường input, `items[].item_id` mới, `status`, `quotation_count=0`, `rejection_reason=null`, `po_id=null`, `version=1`, `created_at`, `updated_at` (UTC). Repository lưu danh sách PR ở JSON hoặc PostgreSQL theo `persistence_backend`. `is_draft=true` → `draft`; mặc định → `awaiting_quotation`. Response tạo thành công là ranh giới sang B2.

**Lưu ý draft:** UI điều hướng bản nháp về B1, nhưng hiện chưa có route chuyển status `draft` sang `awaiting_quotation`; PATCH giữ nguyên status và endpoint upload báo giá từ chối `draft`. Đây là điểm nghẽn của nhánh lưu nháp cần xử lý trước khi dùng như một quy trình tiếp tục hoàn chỉnh.

## Sửa PR đã có

`POST /api/v1/prs/{id}/change-impact` xem ảnh hưởng trước khi sửa; `PATCH /api/v1/prs/{id}?expected_version=N` nhận `PurchaseRequestUpdate` (không sửa `code`), trả `PurchaseRequest` với `version+1`. Chỉnh PR có thể làm báo giá phải đối soát lại và phân tích thành `stale`; xem logic trong [`src/application/procurement/purchase_requests.py`](../../src/application/procurement/purchase_requests.py). `409` khi mã trùng hoặc xung đột version/khóa trạng thái; `422` khi payload sai.

**Điểm cần rà soát:** backend chấp nhận ngân sách 0, danh mục rỗng và ngày quá khứ dù form không cho; `requested_uom` chỉ lấy từ dòng đầu. Nếu một trong các điều kiện này là luật nghiệp vụ, cần đưa vào domain/API.

Nguồn: [`purchaseRequests.tsx`](../../frontend/src/features/purchaseRequests.tsx), [`purchase_request.py`](../../src/domain/purchase_request.py), [`purchase_requests.py`](../../src/infrastructure/repositories/purchase_requests.py), [`procurement.py`](../../src/api/routes/procurement.py).
