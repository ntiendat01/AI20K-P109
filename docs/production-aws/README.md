# Local Docker Compose và production EC2

## Quyết định đã chốt

- Local ưu tiên `docker compose up` chạy toàn bộ stack, với PostgreSQL container và file PDF trên filesystem local.
- Production vẫn chạy toàn bộ application stack bằng Docker trên **một EC2**; deploy thủ công.
- Production dùng PostgreSQL container và filesystem trên persistent Docker volumes của EC2.
- Không dùng Terraform, không đưa SQS/worker topology mới vào phạm vi triển khai ngắn hạn.

Local và production dùng cùng loại storage và Compose topology; khác nhau ở secrets và cách truy cập. Toàn bộ dữ liệu phụ thuộc vào EC2/EBS và chỉ hỗ trợ một backend replica.

## Tài liệu

| File | Nội dung |
| --- | --- |
| [01-current-and-target.md](01-current-and-target.md) | Hiện trạng, kiến trúc mục tiêu và ranh giới cần sửa |
| [02-local-compose.md](02-local-compose.md) | Hợp đồng `docker compose up` tại local |
| [03-production-manual-deploy.md](03-production-manual-deploy.md) | Runbook deploy thủ công toàn bộ stack trên EC2 |
| [04-data-migration-and-operations.md](04-data-migration-and-operations.md) | Migration dữ liệu, backup, rollback và checklist go-live |
| [production-aws.md](production-aws.md) | Các invariant kiến trúc ràng buộc implementation |

## Giới hạn được chấp nhận

- Một EC2 không có high availability; EC2 hỏng hoặc deploy lỗi có thể gây gián đoạn dịch vụ.
- Analysis hiện là background task trong process API; restart container có thể làm analysis đang chạy thất bại và cần chạy lại.
- Mất EC2/EBS có thể làm mất PostgreSQL, file upload, SQLite và Chroma nếu chưa có bản backup độc lập.

Các giới hạn trên chấp nhận được cho rollout sớm khi backup/restore từ EBS hoặc bản backup độc lập đã được diễn tập.

