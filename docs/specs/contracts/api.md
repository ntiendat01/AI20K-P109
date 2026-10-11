# HTTP API Contracts

Prefix đề xuất: `/api/v1`.

## Quy ước chung

- Commands hỗ trợ `Idempotency-Key` khi có thể được retry.
- Mọi response lỗi dùng một envelope thống nhất.
- API không trả local filesystem path, raw provider response hoặc internal prompt.
- Timestamp dùng UTC ISO-8601.

### Error envelope

```json
{
  "error": {
    "code": "QUOTATION_NOT_CONFIRMED",
    "message": "Quotation must be confirmed before analysis.",
    "details": {},
    "correlation_id": "uuid"
  }
}
```

## Upload và extraction

### `POST /prs/{pr_id}/documents`

Multipart upload một file PDF. Intake lưu file bất biến trong `data/uploads/`, cấp `document_id` và tính `content_hash`. `file_path` chỉ dùng nội bộ và không xuất hiện trong public response.

Pipeline không có bước `Document Classifier`; job chuyển trực tiếp từ intake sang OCR extractor.

Thành công:

```http
202 Accepted
```

```json
{
  "document_id": "uuid",
  "filename": "quotation-vendor-a.pdf",
  "content_hash": "sha256",
  "job_id": "uuid",
  "status": "queued"
}
```

### `GET /jobs/{job_id}`

```json
{
  "job_id": "uuid",
  "job_type": "document_extraction | procurement_analysis",
  "status": "queued | running | waiting_for_human | completed | failed",
  "current_step": "intake | ocr | extraction | validation | waiting_for_human | normalization | tco | risk | comparison | decision",
  "progress": 40,
  "resource_id": "quotation-id",
  "error": null,
  "created_at": "ISO-8601 UTC",
  "updated_at": "ISO-8601 UTC"
}
```

Với `document_extraction`, job chuyển sang `waiting_for_human` sau khi OCR, extraction và structural validation hoàn tất. Mọi quotation đều chờ Buyer confirm, không phụ thuộc confidence cao hay thấp.

### `GET /quotations/{quotation_id}`

Trả quotation identity, current extraction draft/confirmed revision và field provenance cần cho UI review. Không trả `source_path`.

Khi quotation chưa được confirm, response phải cung cấp confidence theo từng field:

```json
{
  "quotation_id": "uuid",
  "status": "needs_confirmation",
  "human_confirmation_required": true,
  "confidence_threshold": "0.80",
  "draft_revision_no": 1,
  "extraction": {
    "supplier_name": {
      "value": "Vendor A",
      "confidence": "0.96",
      "source": {"document_id": "uuid", "page_number": 1, "block_id": "p1-b1"}
    },
    "items": [
      {
        "source_item_id": "extracted-item-1",
        "product_name": {
          "value": "Laptop",
          "confidence": "0.92",
          "source": {"document_id": "uuid", "page_number": 1, "block_id": "p1-b8"}
        },
        "unit_price": {
          "value": "15000000.00",
          "confidence": "0.74",
          "source": {"document_id": "uuid", "page_number": 1, "block_id": "p1-b12"}
        }
      }
    ]
  },
  "validation_issues": [
    {
      "field_path": "items[0].unit_price",
      "code": "LOW_CONFIDENCE",
      "severity": "warning",
      "confidence": "0.74"
    }
  ]
}
```

Frontend presentation rule:

- `confidence_threshold` là giá trị từ global config duy nhất, mặc định `0.80`; client không được gửi hoặc override threshold theo quotation.
- `confidence < confidence_threshold`: hiển thị field cảnh báo/đỏ.
- `confidence >= confidence_threshold`: hiển thị field bình thường.
- Tất cả field, kể cả confidence cao, chỉ được dùng cho analysis sau khi Buyer confirm toàn bộ quotation.

### `POST /quotations/{quotation_id}/confirm`

Headers: `Idempotency-Key`, `If-Match: <revision>`.

Request body chứa toàn bộ dữ liệu Buyer đã đối chiếu và xác nhận với tài liệu nguồn. `source_item_id` liên kết item đã xác nhận với item extraction ban đầu. Shipping cost chưa thuộc contract này.

```json
{
  "supplier_name": "Vendor A",
  "currency": "VND",
  "vat_rate": "0.10",
  "vat_included": false,
  "lead_time_days": 7,
  "warranty_months": 12,
  "payment_terms": "Thanh toán trong 30 ngày",
  "items": [
    {
      "source_item_id": "extracted-item-1",
      "product_name": "Laptop",
      "product_code": "LT-01",
      "unit": "cái",
      "quantity": "10",
      "unit_price": "15000000.00"
    }
  ],
  "review_note": null
}
```

Thành công tạo revision immutable mới và trả lại đúng nội dung server đã lưu:

```http
201 Created
```

```json
{
  "quotation_id": "uuid",
  "revision": {
    "revision_id": "uuid",
    "revision_no": 2,
    "status": "confirmed",
    "supplier_id": "server-owned-supplier-id",
    "supplier_name": "Vendor A",
    "currency": "VND",
    "vat_rate": "0.10",
    "vat_included": false,
    "lead_time_days": 7,
    "warranty_months": 12,
    "payment_terms": "Thanh toán trong 30 ngày",
    "items": [
      {
        "source_item_id": "extracted-item-1",
        "product_name": "Laptop",
        "product_code": "LT-01",
        "unit": "cái",
        "quantity": "10",
        "unit_price": "15000000.00"
      }
    ],
    "review_note": null,
    "confirmed_by": "user-id",
    "confirmed_at": "ISO-8601 UTC"
  }
}
```

`supplier_id` do server sở hữu; client không được tự tạo hoặc thay đổi supplier identity trong request confirm. Các giá trị tiền và số lượng dùng decimal string để tránh sai số JSON floating-point.

Nếu còn structural issue có severity chặn confirm, API trả `422 EXTRACTION_VALIDATION_FAILED` cùng danh sách `field_path` và `code`. Low-confidence issue chỉ dùng để cảnh báo, không tự chặn confirm sau khi Buyer đã gửi full confirmed payload.

Nếu revision đã thay đổi: `409 REVISION_CONFLICT`.

## Analysis

### `POST /prs/{pr_id}/analyses`

Preconditions:

- Ít nhất hai confirmed quotation revisions từ hai supplier identities khác nhau.
- Không có quotation đang chờ review nếu policy yêu cầu toàn bộ quotations phải chốt.

Response:

```http
202 Accepted
```

```json
{
  "analysis_id": "uuid",
  "analysis_revision": 1,
  "snapshot_hash": "sha256",
  "job_id": "uuid",
  "status": "queued"
}
```

Retry cùng `Idempotency-Key` trả lại cùng analysis/job.

### `GET /analyses/{analysis_id}`

```json
{
  "analysis_id": "uuid",
  "pr_id": "uuid",
  "analysis_revision": 1,
  "snapshot_hash": "sha256",
  "status": "queued | running | awaiting_buyer_review | pending_manager_approval | needs_input | approved | rejected | failed | superseded",
  "quotation_revision_ids": ["uuid"],
  "tco_results": [],
  "risk_flags": [],
  "comparison_matrix": {},
  "decision_proposal": null,
  "created_at": "ISO-8601 UTC",
  "completed_at": null
}
```

Nếu quotation revision mới xuất hiện, analysis cũ vẫn đọc được nhưng mang `superseded`.

## Buyer review, Manager approval và PO

### `POST /analyses/{analysis_id}/submit-approval`

Buyer-only. Headers: `Idempotency-Key`, `If-Match: <analysis_revision>`.

Buyer gọi endpoint này sau khi đã xem AI recommendation, TCO, risks và comparison:

```json
{
  "analysis_revision": 1,
  "action": "submit | revise",
  "note": null
}
```

Rules:

- `submit` chỉ hợp lệ khi analysis ở trạng thái `awaiting_buyer_review`.
- `submit` tạo immutable Buyer recommendation confirmation và chuyển analysis sang `pending_manager_approval`.
- `revise` yêu cầu `note`, không gửi analysis lên Manager.
- Buyer không được approve supplier hoặc tạo PO.

Response khi submit:

```json
{
  "confirmation_id": "uuid",
  "analysis_id": "uuid",
  "analysis_revision": 1,
  "status": "pending_manager_approval",
  "submitted_by": "buyer-user-id",
  "submitted_at": "ISO-8601 UTC"
}
```

### `POST /analyses/{analysis_id}/decisions`

Manager-only. Headers: `Idempotency-Key`.

```json
{
  "analysis_revision": 1,
  "decision": "approve | revise | reject",
  "selected_supplier_id": "required when approve",
  "reason": "required when revise/reject"
}
```

Rules:

- Manager chỉ được quyết định khi analysis ở trạng thái `pending_manager_approval` và có Buyer recommendation confirmation hợp lệ.
- `approve` chỉ hợp lệ với analysis chưa superseded.
- `selected_supplier_id` phải tồn tại trong snapshot.
- Approve tạo PO draft qua PO service trong transaction/idempotent workflow.

Response approve:

```json
{
  "decision_id": "uuid",
  "status": "approved",
  "purchase_order_id": "uuid"
}
```

### `GET /purchase-orders/{po_id}`

Trả immutable calculation references:

```json
{
  "id": "uuid",
  "code": "PO-...",
  "status": "draft",
  "pr_id": "uuid",
  "analysis_id": "uuid",
  "snapshot_hash": "sha256",
  "quotation_revision_id": "uuid",
  "supplier_id": "uuid",
  "subtotal": "100000.00",
  "shipping_amount": null,
  "tax_amount": "10000.00",
  "total_amount": "110000.00",
  "currency": "VND"
}
```

`shipping_amount` tạm thời nullable và không phải input bắt buộc. `null` có nghĩa là chưa có nghiệp vụ/nguồn tính được xác nhận; không được tự chuyển thành `0.00`. Contract nhập và tính shipping cost sẽ được bổ sung sau khi xác nhận nghiệp vụ, có thể chỉ áp dụng cho shortlist thay vì toàn bộ NCC.

## HTTP status conventions

- `200`: query hoặc idempotent replay hoàn tất.
- `201`: synchronous resource creation nhỏ.
- `202`: long-running extraction/analysis accepted.
- `400`: malformed input.
- `403`: role/object-scope violation.
- `404`: resource không tồn tại trong tenant scope.
- `409`: state/revision/idempotency conflict.
- `422`: schema hợp lệ về JSON nhưng vi phạm field/domain validation.
- `503`: provider/dependency tạm thời unavailable; job có thể retry nội bộ.

## Compatibility note

Endpoint hiện tại `/prs/{id}/analysis` chạy đồng bộ được coi là legacy. Trong migration có thể giữ facade tạm thời, nhưng application service bên dưới phải dùng cùng `Analysis` contract và không giữ orchestration trong FastAPI route.
