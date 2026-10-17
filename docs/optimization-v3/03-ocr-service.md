# Optimization v3 — Phase 3: OCR Service

## Mục tiêu

Tạo OCR service độc lập nhưng chưa đổi callsite của core. Điều này cho phép kiểm
thử transport, readiness và giới hạn tài nguyên trước khi traffic production đi
qua service mới.

## Thành phần đã thêm

- `ocr/Dockerfile`: image chỉ chứa OCR runtime và thư viện hệ thống cần thiết.
- `ocr/requirements-ocr-service.txt`: dependency của service, tách khỏi core.
- `ocr/ocr_service`: FastAPI app, settings và PaddleOCR adapter.
- Compose service `ocr`: không public port, chỉ sẵn sàng trên network nội bộ.

## API

| Endpoint | Chức năng |
| --- | --- |
| `GET /live` | Xác nhận process còn sống. |
| `GET /ready` | Chỉ trả thành công khi model OCR warm-up thành công. |
| `POST /v1/ocr` | Nhận một PDF/PNG/JPEG multipart và trả `OCRResponse` v1. |

Service kiểm tra magic bytes, giới hạn kích thước upload, số trang PDF, token
nội bộ (nếu cấu hình), checksum và xóa file tạm sau khi inference xong. Response
giữ page/line/confidence để core tiếp tục HITL như trước.

## Giới hạn hiện tại

Model vẫn được PaddleOCR tải khi warm-up lần đầu. Phase cutover phải bake hoặc
mount model cache có checksum trước khi vận hành offline. Core cũng chưa gọi
service trong phase này; luồng cũ vẫn hoạt động độc lập.

## Kiểm chứng

`tests/test_ocr_service.py` kiểm tra response versioned, từ chối payload lớn và
authentication nội bộ. Docker runtime chưa đo được ở máy hiện tại do không truy
cập được Docker daemon; cần chạy compose smoke test trong CI hoặc máy Docker.
