# Chuyển evidence sang pgvector và xử lý PDF sang OCR service

## Phạm vi

- PostgreSQL lưu bản ghi evidence, metadata và vector lexical 128 chiều. Backend không cần ChromaDB khi cutover xong.
- OCR service thực hiện trích xuất text PDF, phân loại trang, đọc text gốc và tạo preview. Backend giữ API cho frontend nhưng gọi OCR service để xử lý.
- `pdfplumber` vẫn ở backend để lấy ô bảng cho parser báo giá; các luồng này không dùng PyMuPDF.

## Thứ tự triển khai

1. Dừng ghi dữ liệu và sao lưu database PostgreSQL hiện tại cùng thư mục Chroma `data/chroma`. Dùng `pg_dump`/`pg_restore` để chuyển database, không gắn trực tiếp volume Alpine cũ vào image PostgreSQL Debian mới.
2. Giữ nguyên volume PostgreSQL cũ. Compose dùng volume mới `postgres-vector-data` với image `pgvector/pgvector:0.8.7-pg16`, cùng major PostgreSQL 16. Chỉ khởi động dịch vụ `postgres` trên volume mới và phục hồi bản dump trước khi khởi động backend.
3. Từ thư mục gốc repository, trong môi trường Python tạm thời có `chromadb` và các dependency backend, chạy `python -m scripts.migrate_chroma_evidence_to_pgvector --chroma-dir <bản-sao-data/chroma> --database-url <URL-PostgreSQL-mới>`. Script đọc collection `procurement-evidence-v1`, xác thực từng chunk, tính lại cùng vector lexical và upsert vào PostgreSQL. Chroma chỉ cần trong môi trường chuyển dữ liệu này, không nằm trong image backend mới.
4. Triển khai OCR service và backend từ cùng phiên bản mã nguồn. Backend khởi động sẽ yêu cầu PostgreSQL có extension `vector`; tài khoản database cần quyền `CREATE EXTENSION` lần đầu. Khởi động frontend sau khi backend sẵn sàng.
5. Kiểm tra số bản ghi evidence đã chuyển, phân tích một PR có evidence, trích xuất PDF text/scan và xem preview báo giá trước khi mở lại ghi dữ liệu. Giữ bản dump và volume cũ để có thể quay về phiên bản trước.

## Lưu ý vận hành

- Không khởi động backend mới trên database trống rồi mới phục hồi dữ liệu: startup sẽ tạo schema và bắt đầu phục vụ request.
- Chroma index cũ có thể chứa các revision không còn hiện hành. Script giữ nguyên mọi bản ghi; truy vấn PostgreSQL vẫn lọc theo tenant, case, supplier, loại nguồn và hash tài liệu hiện hành.
- OCR service hiện có PyMuPDF. Các API PDF mới đều kiểm tra token, kích thước file và số trang như API OCR cũ. Giữ `OCR_SERVICE_BASE_URL`, `OCR_SERVICE_TOKEN` và giới hạn upload đồng bộ giữa hai service.
- Volume PostgreSQL cũ vẫn tồn tại sau cutover; không xóa trước khi xác nhận dữ liệu và chức năng trên bản mới.
