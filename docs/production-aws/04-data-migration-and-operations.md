# Dữ liệu và vận hành trên một EC2

## Nơi lưu dữ liệu

| Dữ liệu | Nơi lưu | Backup cần có |
| --- | --- | --- |
| PR, PO, quotation metadata | PostgreSQL named volume `postgres-data` | `pg_dump` hoặc PostgreSQL volume backup |
| PDF upload, workflow/evaluation SQLite, Chroma | `app-data` mount tại `/app/data` | Backup nhất quán volume; dừng ghi khi cần |
| Redis | `redis-data` | Có thể tái tạo nếu ứng dụng không phụ thuộc dữ liệu Redis bền vững |

Không chạy nhiều backend replica. Một EC2 chứa toàn bộ dữ liệu đang hoạt động; mất EC2/EBS sẽ làm gián đoạn dịch vụ và có thể mất dữ liệu kể từ lần backup gần nhất.

## Chuyển từ dữ liệu hiện có

Nguồn có thể gồm JSON, SQLite và `data/uploads/`. Trước khi bật production:

1. Dừng writer và sao lưu toàn bộ thư mục `data/`.
2. Import PR, PO và quotation hiện có vào PostgreSQL theo công cụ chuyển đổi đã kiểm chứng.
3. Giữ PDF ở filesystem dưới `/app/data/uploads`; xác nhận các bản ghi trỏ đúng file và checksum trùng khớp.
4. Giữ workflow/evaluation SQLite và Chroma trong `/app/data`.
5. Đối soát record count, trạng thái, quan hệ ID và checksum trước khi cho phép ghi.

## Backup và phục hồi

- Thực hiện `pg_dump` định kỳ; mã hóa và lưu bản backup độc lập với EC2.
- Tạo EBS snapshot trước deploy quan trọng và theo lịch vận hành.
- Backup `app-data` đồng bộ với database khi cần consistency giữa metadata và file; kiểm tra phục hồi định kỳ.
- Lưu Compose, image tag, `.env.production` an toàn và hướng dẫn khôi phục ở nơi có thể truy cập khi EC2 hỏng.
- Không xóa Docker volumes trong thao tác cập nhật thông thường.

## Monitoring

- Container health/restart và log backend, OCR, Nginx, PostgreSQL.
- EC2 CPU, memory, disk usage và disk I/O.
- PostgreSQL connection/error và dung lượng volume.
- Ứng dụng: HTTP 5xx, lỗi upload/extraction/analysis, thời gian xử lý và request ID.

## Checklist trước go-live

- [ ] `docker compose up --build` local chạy PostgreSQL và filesystem.
- [ ] Production Compose dùng named volumes cho PostgreSQL và `/app/data`.
- [ ] Mật khẩu PostgreSQL không còn giá trị mặc định và `.env.production` không được commit.
- [ ] PostgreSQL port không public; chỉ cổng ứng dụng cần thiết được mở.
- [ ] Backup/restore PostgreSQL và file volume đã được thử.
- [ ] Có cảnh báo dung lượng disk và quy trình khôi phục khi EC2/EBS gặp lỗi.
- [ ] Deploy/rollback image đã được diễn tập mà không xóa data volumes.
