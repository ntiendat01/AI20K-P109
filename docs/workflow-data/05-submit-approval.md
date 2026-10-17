# Bước 5 — Buyer xem đề xuất và gửi Manager duyệt

**Input:** `ProcurementAnalysis.status=awaiting_buyer_review`, `review.status=proposed`, `analysis_id`, PR + báo giá cùng `snapshot_revision`; ghi chú Buyer tùy chọn. **UI:** `/purchase-requests/{id}/workflow/5`. `GET /api/v1/recommendations/{recommendation_id}/review` và `/sources/{quotation_id}` cho phép xem bằng chứng/nguồn của đề xuất còn hiệu lực.

## Payload và output

`POST /api/v1/analyses/{analysis_id}/submit-approval` chỉ cho vai trò `procurement`:

```json
{"note": "Ưu tiên NCC có thời gian giao 7 ngày"}
```

`BuyerRecommendationSubmission.note` là `string | null`; UI giới hạn textarea 1000 ký tự, model API không có giới hạn độ dài tương ứng. Route kiểm tra `ensure_current` trước khi chuyển trạng thái. Response là object gồm:

```json
{
  "analysis_id": "<analysis-id>",
  "analysis_revision": 1,
  "submitted_by": "<buyer-id>",
  "submitted_at": "<datetime>",
  "note": "Ưu tiên NCC có thời gian giao 7 ngày",
  "status": "pending_manager_approval",
  "pr_status": "pending_approval"
}
```

## Ghi và chuyển trạng thái

1. Route lấy run theo `analysis_id`, xác nhận snapshot PR + báo giá chưa đổi.
2. `PurchaseRequestRepository.submit_for_approval()` yêu cầu PR đang `comparing`; chuyển PR sang `pending_approval`, xóa `rejection_reason` cũ.
3. `ProcurementWorkflow.submit_buyer_review()` yêu cầu analysis đang `awaiting_buyer_review`; ghi `buyer_confirmation{analysis_id, analysis_revision, submitted_by, submitted_at, note}` và chuyển analysis sang `pending_manager_approval` trong SQLite.
4. UI hiển thị trạng thái chờ; PR và báo giá bị khóa chỉnh sửa ở các màn wizard.

Tại ranh giới này, `review`/`decision_proposal` cung cấp `preferred_supplier_id`, giải trình và ranking; `tco_results[]` cung cấp số liệu so với ngân sách. Ghi chú Buyer là thông tin bổ sung, không sửa kết quả phân tích.

**Điểm cần rà soát:** thao tác ghi PR và ghi analysis ở hai kho khác nhau, không nằm trong một transaction duy nhất. Nếu lần ghi analysis lỗi sau khi PR đổi trạng thái, cần cơ chế reconcile/rollback để tránh `pending_approval` mà thiếu `buyer_confirmation`.

Nguồn: [`procurementWorkflow.tsx`](../../frontend/src/features/procurementWorkflow.tsx), [`procurement_workflow.py`](../../src/api/routes/procurement_workflow.py), [`workflow.py`](../../src/application/procurement/workflow.py), [`purchase_requests.py`](../../src/infrastructure/repositories/purchase_requests.py).
