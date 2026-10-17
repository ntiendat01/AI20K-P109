# Deploy production thủ công: toàn bộ trên EC2

## Phạm vi

Toàn bộ ứng dụng, PostgreSQL, Redis, OCR và file được chạy bằng Docker Compose trên một EC2. Dữ liệu PostgreSQL và filesystem nằm trên named volumes gắn với disk của EC2. Không cần RDS hoặc S3.

## Chuẩn bị EC2

- Cài Docker Engine và Docker Compose plugin.
- Đủ disk cho image, PostgreSQL, PDF upload, Chroma và SQLite; theo dõi dung lượng thường xuyên.
- Security group chỉ mở cổng cần thiết cho HTTPS/HTTP và SSH từ IP quản trị; PostgreSQL không publish ra internet.
- Chuẩn bị DNS/TLS tại Nginx hoặc lớp proxy đã chọn.
- Lưu `.env.production` ngoài Git với quyền đọc hạn chế.

## Cấu hình

Tạo `.env.production` từ [`.env.production.example`](../../.env.production.example). Đặt `POSTGRES_PASSWORD` thành chuỗi chữ và số dài, ngẫu nhiên để Compose tạo `DATABASE_URL` hợp lệ. Đặt các API key cần thiết cho LLM/OCR.

Production Compose tạo schema PostgreSQL khi backend khởi động và lưu dữ liệu trong các named volume `postgres-data`, `app-data`, `redis-data`.

## Deploy

1. Tạo bản backup/snapshot EC2 EBS theo runbook vận hành và lưu image tag hiện tại.
2. Copy source/config hoặc image đã build lên EC2.
3. Copy `docker-compose.production.yml` và `.env.production` lên EC2; xác nhận file secrets không được commit hoặc expose.
4. Build image trên EC2 và khởi động:

   ```bash
   docker compose --env-file .env.production -f docker-compose.production.yml up --build -d
   ```

5. Kiểm tra `docker compose ps`, log backend/OCR, health endpoint, tạo PR, upload và đọc lại PDF.
6. Ghi lại release: thời gian, image tag, commit, operator và kết quả smoke test.

## Backup và rollback deploy

- PostgreSQL volume chứa PR/PO/quotation; `/app/data` chứa file, SQLite workflow/evaluation và Chroma. Backup cần nhất quán và phải có kiểm tra restore.
- Trước deploy quan trọng, dừng ghi hoặc tạo backup PostgreSQL bằng `pg_dump`; đồng thời backup volume `app-data` và Compose/env đã che secrets.
- Rollback ứng dụng bằng image tag trước đó. Không xóa named volumes khi thay image hoặc chạy `docker compose down`.
- Một EC2 là single point of failure. EBS snapshot hoặc bản backup ngoài EC2 là cần thiết để phục hồi sau mất máy/disk.

## Giới hạn

Chỉ chạy một backend replica vì SQLite workflow/evaluation, Chroma và file đều ở local volume. Analysis đang chạy có thể bị gián đoạn khi container/reboot EC2 restart; người dùng cần chạy lại analysis đó.
