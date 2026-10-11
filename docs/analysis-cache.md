# Cache lần chạy phân tích

## Phạm vi cache

Khóa kết quả là cặp `(pr_id, snapshot_revision)`. Khi snapshot giống hệt và
lần chạy gần nhất là `awaiting_review` hoặc `approved`, API trả lại cùng
`analysis_id` mà không gọi graph, tool hay Decision LLM. `?force=true` chỉ dành
cho vai trò `procurement`; tham số này luôn tạo lần chạy graph mới, nhưng vẫn có
thể dùng evidence chunks đã ingest an toàn.

Một lần chạy `technical_failure`, `stale`, `needs_input`, `repairable` không
được dùng làm cache kết quả. Lần chạy đang `running` cùng snapshot được trả lại
nguyên trạng để không tạo hai worker song song.

## Cache evidence

SQLite `procurement-workflow.sqlite` có bảng `evidence_cache`. Khóa cache gồm
tenant, PR, `chunk_id`, `document_hash` và `chunk_hash`. Vì vậy chỉ skip ingest
khi đúng chunk nguồn của đúng PR không đổi; nội dung file hoặc một chỉnh sửa
Buyer có audit ID mới sẽ có khóa mới và được ingest lại. Ghi cache chỉ sau khi
adapter ingest thành công; lỗi không tạo mục cache giả.

## Ngày chạy trong snapshot

`ProcurementWorkflow.revision()` hiện đưa
`datetime.now().date().isoformat()` vào trường `as_of_date` trước khi băm.
Vì thế, dù PR và báo giá không đổi, snapshot khác khi qua ngày mới và kết quả
hôm trước không còn hit cache. Đây là hành vi hiện hữu được giữ nguyên theo
P3-T2; nó giúp các quyết định phụ thuộc ngày không vô tình dùng kết quả cũ,
nhưng cũng tăng số lần LLM/tool chạy ở lần mở đầu ngày.

Đề xuất backlog: xác nhận với chủ sở hữu policy liệu ngày chạy thực sự là đầu
vào quyết định. Nếu không, tách nó khỏi hash (hoặc version hoá riêng policy
theo ngày) trong một task có migration và đánh giá rủi ro cache rõ ràng.
