# Optimization v3 — Phase 2: OCR Contract

## Mục tiêu

Định nghĩa boundary ổn định giữa core API và OCR service trước khi thay đổi bất
kỳ callsite nào. Contract này là schema cho `POST /v1/ocr` và các lỗi của nó.

## Contract đã thêm

`src/ocr/contracts.py` định nghĩa:

- `OCRResponse`: schema version, request ID, checksum tài liệu, engine/model
  version, page, line, confidence và warnings.
- `OCRErrorResponse`: mã lỗi ổn định và cờ `retryable`.
- `OCRErrorCode`: invalid document, payload quá lớn, quá số trang, service bận,
  không sẵn sàng và lỗi xử lý.

Core cần validate response theo contract này trước khi chuyển OCR output sang
LLM/HITL. Service cần trả cùng schema cho mọi request thành công.

## Cấu hình mới

`Settings` có các biến chuẩn bị cho migration:

| Biến | Mục đích |
| --- | --- |
| `OCR_MODE` | `local`, `shadow` hoặc `remote`; mặc định `local`. |
| `OCR_SERVICE_BASE_URL` | Base URL nội bộ của OCR service. |
| `OCR_SERVICE_TOKEN` | Credential service-to-service. |
| `OCR_SERVICE_TIMEOUT_SECONDS` | Timeout tổng cho OCR client. |
| `OCR_MAX_UPLOAD_BYTES` | Giới hạn upload trước khi gửi sang OCR. |
| `OCR_MAX_PAGES` | Giới hạn số trang được xử lý. |

`PADDLEOCR_BASE_URL` chưa bị dùng lại hoặc xóa trong phase này để tránh thay đổi
ngầm hành vi cũ.

## Kiểm chứng

`tests/test_ocr_contract.py` kiểm tra preservation của line/confidence, checksum
không hợp lệ và error payload retryable. Chưa có HTTP endpoint ở phase này;
endpoint được triển khai ở phase tiếp theo.
