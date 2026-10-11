# Domain and Storage Contract

## Aggregate boundaries

### PurchaseRequest aggregate

Sở hữu nhu cầu mua hàng và lifecycle tổng quát. Không sở hữu OCR, analysis internals hoặc PO calculation.

```text
PurchaseRequest
  id, tenant_id, code, creator_id
  category, requested_quantity, requested_uom
  target_currency, estimated_budget, delivery_due_date
  status, version
  created_at, updated_at
```

Trạng thái tối thiểu:

```text
draft → awaiting_quotation → comparing → pending_approval
      → rejected | approved
```

### Document aggregate

Metadata của file PDF immutable. Trong phạm vi ứng dụng nội bộ hiện tại, binary được lưu tại `data/uploads/`; thiết kế chưa yêu cầu object storage hoặc microservice intake riêng.

```text
Document
  id, tenant_id, pr_id
  filename, media_type: application/pdf, byte_size
  content_hash, file_path
  status: uploaded | processing | ready | failed
  created_by, created_at
```

`file_path` là internal storage field và không được trả qua public API. `content_hash` dùng cho audit, provenance và phát hiện upload trùng; file đã lưu không bị ghi đè.

### Document representation

Kết quả duy nhất từ OCR extractor, không có `Document Classifier` trung gian.

```text
DocumentRepresentation
  id, document_id
  engine: paddleocr | pymupdf
  engine_version, created_at

DocumentBlock
  id, representation_id
  page_number, block_id
  kind: text | table_cell
  text, bounding_box_json, confidence
```

Representation và blocks là dữ liệu OCR nguồn. Extraction Service đọc chúng nhưng không ghi đè nội dung.

### Quotation aggregate

`Quotation` là identity ổn định; dữ liệu thay đổi nằm trong revision.

```text
Quotation
  id, tenant_id, pr_id, supplier_id, document_id
  current_version_no, current_confirmed_revision_id?
  status: extracting | needs_confirmation | confirmed | superseded | failed
  created_at

QuotationRevision
  id, quotation_id, revision_no
  status: confirmed | superseded
  supplier_name, currency, vat_rate, vat_included
  lead_time_days, warranty_months, payment_terms, review_note
  confirmed_by, confirmed_at
  schema_version, created_at
```

`QuotationRevision` chỉ hình thành từ full payload Buyer đã xác nhận. Machine extraction không phải quotation revision. Mỗi lần Buyer confirm lại tạo revision mới; không mutate revision đã confirm.

`Quotation.current_version_no` là optimistic concurrency counter chung cho aggregate. Ví dụ extraction draft mang version `1`; confirm với `If-Match: 1` tạo confirmed revision `2`. Draft nằm trong `quotation_extractions`, còn confirmed revision nằm trong `quotation_revisions`, nhưng chúng dùng cùng chuỗi version để API không có hai concurrency token khác nhau.

```text
QuotationItemRevision
  id, quotation_revision_id
  source_item_id
  product_name, product_code, unit
  quantity_decimal, unit_price_decimal
  created_at
```

`supplier_id` do server sở hữu và được resolve từ quotation/supplier registry; client không được ghi đè identity này.

### Extraction draft, validation và provenance

Mỗi lần chạy Extraction Service tạo một extraction riêng, trước HITL-1:

```text
QuotationExtraction
  id, quotation_id, document_representation_id
  version_no, provider, model
  schema_valid
  human_confirmation_required: true
  applied_confidence_threshold
  status: extracted | validated | failed
  created_at
```

```text
ExtractedField
  id, quotation_extraction_id, source_item_id?, field_path
  raw_value, parsed_value, confidence
  document_id, page_number, block_id, bounding_box, source_text

ValidationIssue
  id, quotation_extraction_id
  field_path, code
  severity: warning | blocking
  confidence?, details_json
```

Global config có một `confidence_threshold`, mặc định `0.80`. Threshold được áp dụng chung cho mọi field và không được override theo quotation. Giá trị đã áp dụng được snapshot trong `QuotationExtraction.applied_confidence_threshold` để audit.

- `confidence < threshold` tạo warning để frontend tô đỏ.
- `confidence >= threshold` hiển thị bình thường.
- Low confidence không chặn Buyer confirm.
- Structural issue có severity `blocking` có thể chặn confirm.
- Mọi extraction đều chuyển sang `needs_confirmation`, không có auto-confirm.

`raw_value` không bị thay bởi human correction. Giá trị Buyer xác nhận nằm trong `QuotationRevision`/`QuotationItemRevision`; `source_item_id` liên kết item confirmed với extraction item ban đầu.

### Analysis aggregate

```text
Analysis
  id, tenant_id, pr_id
  revision_no, snapshot_hash
  status: queued | running | awaiting_buyer_review | pending_manager_approval | needs_input | approved | rejected | failed | superseded
  recommendation_id
  created_by, created_at, completed_at

AnalysisInput
  analysis_id, quotation_revision_id, content_hash

AnalysisArtifact
  id, analysis_id
  artifact_type: normalization | tco | risk | comparison | decision
  schema_version, producer_version
  payload_json, input_hash, created_at
```

Artifact types tách biệt; không lưu raw OCR và evidence trong cùng row/payload.

Analysis execution order được lưu/quan sát theo pipeline:

```text
normalization
→ calculate_tco ─→ compare_suppliers ─┐
→ analyze_risks ──────────────────────┤
                                     → decision
```

`normalization` chỉ nhận confirmed quotation revisions. Nếu thiếu UOM/FX mapping, normalized field liên quan là `null` và artifact có status `needs_mapping`; không fallback về source value.

### Buyer recommendation confirmation

Buyer review là boundary riêng sau Decision LLM và trước Manager approval.

```text
BuyerRecommendationConfirmation
  id, tenant_id, pr_id
  analysis_id, analysis_revision
  decision_proposal_artifact_id
  action: submit | revise
  note, buyer_id, idempotency_key
  created_at
```

Chỉ `submit` mới chuyển analysis từ `awaiting_buyer_review` sang `pending_manager_approval`. Buyer không được tạo `ApprovalDecision` hoặc PO.

### Manager approval aggregate

```text
ApprovalDecision
  id, tenant_id, pr_id
  analysis_id, analysis_revision
  buyer_confirmation_id
  decision: approve | revise | reject
  selected_supplier_id?, reason, actor_id, idempotency_key
  created_at
```

`selected_supplier_id` bắt buộc khi approve và phải thuộc analysis snapshot. `reason` bắt buộc khi revise/reject.

Manager decision chỉ hợp lệ khi analysis đang `pending_manager_approval`, có Buyer confirmation action `submit`, và snapshot chưa `superseded`.

### PurchaseOrder aggregate

PO được tạo bởi `PurchaseOrderService`, không bởi LangGraph hoặc LLM.

> **Business decision pending — shipping cost:** Chưa đưa shipping cost vào quotation contract hoặc bắt Buyer/Finance nhập cho mọi NCC. Nguồn, thời điểm và phạm vi tính shipping cần được xác nhận lại. Không được dùng `0` để biểu diễn "chưa biết".

```text
PurchaseOrder
  id, tenant_id, code, pr_id
  approval_decision_id, analysis_id, snapshot_hash
  supplier_id, quotation_revision_id
  subtotal, shipping_amount?, tax_amount, total_amount, currency
  status: draft | cancelled
  approver_id, approved_at, created_at
```

`shipping_amount` là nullable. `null` nghĩa là nghiệp vụ/nguồn tính chưa được xác nhận và không được tự chuyển thành `0`.

### Workflow job aggregate

```text
WorkflowJob
  id, tenant_id, pr_id
  job_type: document_extraction | procurement_analysis
  status: queued | running | waiting_for_human | completed | failed
  current_step
  progress, resource_id, error_json
  idempotency_key?, input_hash
  created_at, updated_at

WorkflowJobEvent
  id, job_id
  node, status: started | completed | failed
  attempt, error_json?, created_at
```

Các step hợp lệ:

```text
intake | ocr | extraction | validation | waiting_for_human
| normalization | tco | risk | comparison | decision
```

Document extraction chuyển sang `waiting_for_human` sau validation với mọi mức confidence.

## Relational tables đề xuất

```text
users
purchase_requests
suppliers
documents
document_representations
document_blocks
quotations
quotation_extractions
quotation_revisions
quotation_item_revisions
extracted_fields
validation_issues
workflow_jobs
workflow_job_events
analyses
analysis_inputs
analysis_artifacts
buyer_recommendation_confirmations
approval_decisions
purchase_orders
purchase_order_items
outbox_events
```

## Evidence/vector index — outside the current pipeline

Evaluator/grounding không tham gia pipeline hiện tại. Nếu sau này cần search/RAG, metadata authoritative nằm trong relational DB hoặc được tái tạo từ document/provenance; vector store chỉ chứa index:

```text
chunk_id
tenant_id
pr_id
document_id
quotation_revision_id
source_kind: original_document | confirmed_revision
page_number
content_hash
embedding
```

Không ingest chung một nội dung “original” và “edited” mà thiếu `source_kind`/revision. Xóa vector index không được làm mất dữ liệu nghiệp vụ.

## Uniqueness và concurrency

- `documents(tenant_id, content_hash)` có thể deduplicate binary.
- `document_blocks(representation_id, block_id)` unique.
- `quotation_extractions(quotation_id, version_no)` unique.
- `quotation_revisions(quotation_id, revision_no)` unique.
- `quotation_item_revisions(quotation_revision_id, source_item_id)` unique khi `source_item_id` không null.
- `analyses(pr_id, revision_no)` unique.
- `buyer_recommendation_confirmations(idempotency_key)` unique.
- `approval_decisions(idempotency_key)` unique.
- `purchase_orders(approval_decision_id)` unique.
- Update aggregate dùng optimistic version; không dùng silent last-write-wins.
- Confirm quotation so sánh `If-Match` với `Quotation.current_version_no`; mismatch trả revision conflict và không tạo revision mới.

## Migration constraints

- JSON repositories hiện tại chỉ được migrate sau khi có script kiểm đếm trước/sau.
- Không xóa JSON/SQLite cũ trong cùng release migration đầu tiên.
- Chạy dual-read validation hoặc export backup trước khi cutover.
- Chroma collection hiện tại được coi là disposable derived data.
