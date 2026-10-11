# Pipeline Contract

## Canonical flow

```text
UploadedDocument
→ DocumentRepresentation
→ ExtractionDraft
→ ValidatedExtraction
→ HITL-1 bắt buộc / ConfirmedQuotationRevision
→ NormalizedQuotation
→ ┬─ TCOResult ─→ SupplierComparison ─┐
  └─ RiskAssessment ──────────────────┤
                                     ▼
                               DecisionProposal
→ HITL-2 / BuyerRecommendationConfirmation
→ ManagerApprovalDecision
→ PurchaseOrder
```

## Common artifact envelope

```json
{
  "artifact_id": "uuid",
  "artifact_type": "normalized_quotation",
  "schema_version": "1.0",
  "tenant_id": "tenant-id",
  "pr_id": "pr-id",
  "input_artifact_ids": ["uuid"],
  "input_hash": "sha256",
  "producer": "normalization-service",
  "producer_version": "1.0",
  "created_at": "ISO-8601 UTC",
  "payload": {}
}
```

## Component boundaries

### Document Intake & Storage

Input: upload metadata + PDF bytes/stream.

Output: `UploadedDocument` (`document_id`, `filename`, `file_path`, `content_hash`).

Responsibilities:

- Lưu file PDF vào `data/uploads/` một cách bất biến.
- Cấp định danh `document_id` và tính `content_hash` để phục vụ audit/provenance.
- Thiết kế tối giản cho ứng dụng nội bộ (không cần microservice intake riêng biệt hay deep magic-byte inspection phức tạp).

### OCR Extractor

Input: `UploadedDocument`.

Output `DocumentRepresentation`:

```json
{
  "document_id": "uuid",
  "pages": [
    {
      "page_number": 1,
      "blocks": [
        {
          "block_id": "p1-b1",
          "kind": "text | table_cell",
          "text": "...",
          "bounding_box": [0, 0, 100, 30],
          "confidence": 0.97
        }
      ]
    }
  ],
  "engine": "paddleocr | pymupdf",
  "engine_version": "string"
}
```

- Chạy bộ trích xuất OCR duy nhất hiện tại để lấy text, bảng biểu và tọa độ bounding box (`bbox`).
- *Lưu ý:* Bỏ qua bộ phân loại `Document Classifier` trung gian để tối giản hóa luồng xử lý; trích xuất trực tiếp từ file PDF.

### Extraction Service

Input: `DocumentRepresentation`.

Output: `ExtractionDraft` gồm supplier, items, commercial terms và field-level provenance.

Rules:

- Document content được coi là untrusted data.
- Structured output phải qua schema parser.
- Field không có trong tài liệu trả `null`, không tự đoán.
- Không normalize UOM/currency tại đây.

### Extraction Validator

Input: `ExtractionDraft`.

Output: `ValidatedExtraction`:

```json
{
  "schema_valid": true,
  "human_confirmation_required": true,
  "issues": [
    {
      "field_path": "items[0].unit_price",
      "code": "LOW_CONFIDENCE",
      "severity": "warning",
      "confidence": "0.74"
    }
  ]
}
```

Rules:

- `confidence_threshold` là **cấu hình toàn cục duy nhất** (Global Config, mặc định `0.80`), áp dụng chung cho mọi trường thông tin.
- Validator chỉ kiểm schema, completeness và so sánh điểm tin cậy với ngưỡng toàn cục `0.80`.
- Bất kỳ trường nào có `confidence < 0.80` đều được đưa vào danh sách `issues` để Frontend hiển thị cảnh báo/tô đỏ cho Buyer kiểm tra. Mọi extraction đều chuyển sang bước Buyer confirm (HITL-1).
- `confidence >= 0.80`: frontend hiển thị field bình thường.
- Confidence chỉ giúp Buyer ưu tiên kiểm tra; không tự động xác nhận bất kỳ field nào.
- Structural errors như sai kiểu, thiếu field bắt buộc hoặc tổng tiền không khớp vẫn nằm trong `issues` và có thể chặn confirm theo validation rules riêng.

### HITL-1 / Quotation Review Service

Input: `ExtractionDraft` hiện tại + full confirmed payload từ Buyer + expected revision từ `If-Match`.

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

Output: immutable `ConfirmedQuotationRevision`.

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

Rules:

- Mọi extraction đều phải đi qua HITL-1, không có nhánh tự động bỏ qua dựa trên confidence.
- Confirm tạo revision mới; không mutate revision cũ.
- `supplier_id` do server sở hữu và được resolve từ quotation/supplier registry.
- `source_item_id` phải thuộc extraction draft hiện tại hoặc được đánh dấu là item Buyer thêm mới theo contract mở rộng sau này.
- Confirmed revision giữ tham chiếu document/provenance nhưng không ghi đè raw extraction.
- Shipping cost không thuộc confirmed quotation contract trong khi nghiệp vụ chưa được chốt.
- Monetary values và quantity truyền qua boundary dưới dạng decimal string.

### Normalization Service

Input duy nhất: confirmed quotation revisions + target UOM/currency + rule version.

Output:

```json
{
  "quotation_revision_id": "uuid",
  "rule_version": "uom-fx-v1",
  "status": "normalized | needs_mapping",
  "items": [
    {
      "source_quantity": "2",
      "source_uom": "box",
      "source_unit_price": "100000",
      "source_currency": "VND",
      "normalized_quantity": "20",
      "normalized_uom": "piece",
      "normalized_unit_price": "10000",
      "normalized_currency": "VND",
      "rule_id": "box-10-piece"
    }
  ],
  "issues": []
}
```

Nếu thiếu mapping/rate, normalized fields liên quan phải `null`; không fallback âm thầm về source value.

### Analysis tools

`calculate_tco`:

- Input: normalized quotations.
- Output: supplier-level TCO và calculation breakdown.
- Không đọc DB hoặc gọi LLM.

`analyze_risks`:

- Input: normalized quotations + immutable PR snapshot.
- Output: structured risk flags.
- Không sửa ranking.

`compare_suppliers`:

- Input: normalized quotations + TCO results.
- Output: matrix theo `total_tco`, `lead_time_days`, `warranty_months`.
- Không gọi LLM và không tạo recommendation.

### Decision LLM

Input: `DecisionContext` chỉ gồm TCO, comparison, risks, PR constraints và top-N.

Output: `DecisionProposal`:

```json
{
  "status": "proposed | needs_input",
  "preferred_supplier_id": "supplier-id",
  "ranked_supplier_ids": ["supplier-id"],
  "rationale": "...",
  "tradeoffs": [],
  "input_artifact_ids": ["uuid"]
}
```

LLM không được:

- tạo lại TCO;
- thay normalized facts;
- tạo PO;
- đánh dấu approved;
- tham chiếu supplier không có trong input.

Sau khi Decision LLM tạo `DecisionProposal`, analysis chuyển thẳng sang `awaiting_buyer_review`. Pipeline không chạy evaluator, grounding gate hoặc auto-repair trung gian.

### HITL-2 / Buyer Recommendation Review

Input: `DecisionProposal` cùng TCO, risk flags và supplier comparison thuộc cùng analysis snapshot.

Buyer bắt buộc xem recommendation sau khi AI tạo xong và chọn một trong hai hành động:

- `submit`: xác nhận đã review và gửi recommendation lên Manager.
- `revise`: yêu cầu chỉnh dữ liệu/analysis trước khi gửi Manager.

Output: immutable `BuyerRecommendationConfirmation` chứa `analysis_id`, `analysis_revision`, `decision_proposal_id`, `buyer_id`, `action`, `note` và timestamp.

Chỉ action `submit` mới chuyển analysis sang `pending_manager_approval`. Buyer không có quyền approve hoặc tạo PO.

### Manager Approval

Input: analysis ở trạng thái `pending_manager_approval` và Buyer recommendation confirmation tương ứng.

Manager chọn `approve | revise | reject`:

- `approve`: chọn supplier thuộc analysis snapshot và chuyển sang PO Service.
- `revise`: trả lại Buyer/workflow với reason bắt buộc.
- `reject`: kết thúc vòng approval với reason bắt buộc.

Manager không được duyệt analysis chưa qua Buyer submit hoặc analysis đã `superseded`.

### PurchaseOrder Service

Input: valid approval decision + approved analysis snapshot.

Output: one idempotent draft PO.

Service tự kiểm supplier/revision/amount từ snapshot; không lấy amount từ rationale của LLM.

## Pipeline execution rules

- Mỗi node ghi job event `started/completed/failed`.
- Retry node không được tạo artifact trùng: uniqueness dựa trên `artifact_type + input_hash + producer_version`.
- Resume bắt đầu tại node chưa hoàn tất gần nhất.
- Timeout/retry policy nằm tại adapter boundary, không nằm trong domain tool.
