# Optimization v3 — Phase 4: Remote Client and Shadow Mode

## Mục tiêu

Kết nối core với OCR service mà không đổi traffic mặc định. Agent intake chọn OCR
mode qua cấu hình; luồng parser Tesseract vẫn giữ nguyên cho đến phase cutover.

## Cách hoạt động

| `OCR_MODE` | Hành vi |
| --- | --- |
| `local` | Mặc định. Dùng PaddleOCR cục bộ như trước. |
| `shadow` | Trả kết quả local; gọi remote để so sánh và log kết quả. Remote lỗi không ảnh hưởng request. |
| `remote` | Dùng OCR service cho các tài liệu thiếu text layer. |

`RemoteOCRClient` gửi multipart qua `POST /v1/ocr`, đính kèm request ID và token
nội bộ nếu có. Response bắt buộc validate theo `OCRResponse`, sau đó được chuyển
về JSON `pages/raw_text/lines` tương thích với agent intake hiện tại.

## Bảo vệ tại client

- Kiểm tra kích thước file trước khi upload.
- Timeout do `OCR_SERVICE_TIMEOUT_SECONDS` quản lý.
- HTTP/network failures thành `OCRServiceError` có cờ `retryable`.
- Shadow mode luôn ưu tiên local result và chỉ log metadata so sánh.

## Kiểm chứng

`tests/test_remote_ocr_client.py` dùng HTTP mock để kiểm tra upload contract,
error retryable và behavior của shadow mode. OCR mode vẫn mặc định `local`; chưa
có traffic production nào bị chuyển trong phase này. `tests/conftest.py` cũng
tắt LangSmith tracing để test không gửi telemetry hay credential ra mạng.
