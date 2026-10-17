# Hợp đồng Docker Compose local

## Mục tiêu

Một lệnh sau phải tạo môi trường dùng được cho developer:

```powershell
docker compose up --build
```

Local dùng PostgreSQL container và filesystem local. Không cần AWS account, S3 hay RDS để chạy luồng chính.

## Services mục tiêu

| Service | Trách nhiệm | Dữ liệu local |
| --- | --- | --- |
| `frontend` | Build/phục vụ React UI | Không cần persistent volume |
| `backend` | FastAPI API và business workflow | Kết nối PostgreSQL; đọc/ghi `data/uploads` qua local object-storage adapter |
| `ocr` | OCR PDF | Không là nơi lưu dữ liệu chuẩn |
| `redis` | Giữ nguyên để tương thích Compose hiện tại cho tới khi được loại bỏ có kiểm chứng | Volume Redis nếu service vẫn cần persistence |
| `postgres` | Transactional system of record local | Named volume `postgres-data` |

## Configuration local bắt buộc

`.env` local không commit cần có các giá trị theo ý nghĩa sau:

```dotenv
APP_ENV=development
DATABASE_URL=postgresql://<local-user>:<local-password>@postgres:5432/<local-db>
STORAGE_PROVIDER=filesystem
UPLOAD_DIR=/app/data/uploads
```

Tên biến cuối cùng có thể thay đổi khi implementation chốt, nhưng không được dùng đường dẫn local làm dữ liệu public/API contract.

## Quy trình khởi động local

1. Sao chép `.env.example` thành `.env` và điền API key chỉ dùng cho development.
2. Chạy `docker compose up --build`.
3. Backend tự tạo bảng PostgreSQL cần thiết khi khởi động lần đầu sau khi PostgreSQL healthy.
4. Kiểm tra health endpoint backend/OCR và tạo một PR, upload PDF, xác nhận quotation, chạy analysis.
5. Restart toàn bộ Compose và xác nhận PR/quotation/analysis đã hoàn tất vẫn còn trong PostgreSQL; PDF vẫn đọc được từ `data/uploads`.

Không cần service hoặc lệnh migration riêng cho schema hiện tại.

## Tiêu chí hoàn thành local

- Không cần dịch vụ AWS để chạy test integration.
- Tắt/bật Compose không làm mất dữ liệu PostgreSQL volume hoặc PDF local.
- PR/PO/quotation mới không còn ghi JSON; workflow/evaluation SQLite vẫn tồn tại trong `data/` và phải được giữ bởi volume local.
- Cùng một test suite chạy được với PostgreSQL local và production EC2.

## Điều không làm ở local

- Không cần AWS service để chạy local hoặc production hiện tại.
- Không sao chép credential production vào `.env` local.
- Không để container backend lưu source document bên trong writable layer của container.

