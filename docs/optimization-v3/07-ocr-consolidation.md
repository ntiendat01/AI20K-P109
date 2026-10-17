# Optimization v3 — OCR Consolidation

## Quyết định

`ocr/` tiếp tục là service OCR độc lập. `src/ocr/` là boundary của backend,
chứa contract HTTP và client; nó không chứa model hoặc inference runtime.

Core dùng đúng một luồng đọc tài liệu: `PDFTextExtractor` đọc text layer theo
từng trang, rồi gọi OCR service chỉ cho trang thiếu text. Cả API parser và
LangGraph intake cùng dùng luồng này.

## Những phần đã bỏ khỏi core

- `PaddleOCRHostedClient` và mọi import `paddleocr` trong backend.
- Tesseract fallback cho PDF scan.
- `local` và `shadow` OCR mode.
- Serialize/parse JSON giữa remote OCR client và parser.

PaddleOCR chỉ được cài qua `ocr/requirements-ocr-service.txt` trong image OCR.
`requirements.txt` chỉ dành cho backend/developer tooling; local development
chạy OCR service qua Compose hoặc khởi động service riêng tại cổng 8080.

## Invariants

- OCR response vẫn giữ page, line và confidence theo `OCRResponse` v1.
- Trang có text layer không gọi OCR.
- PDF mixed chỉ OCR các trang thiếu text, không ghi đè text layer còn lại.
- Lỗi service vẫn được biểu diễn bằng `OCRServiceError` có `retryable`.

## Regression gate

Chạy các test contract, service, remote client, parser và agent extraction.
Benchmark 19 tài liệu phải giữ hoặc cải thiện số liệu đã ghi trong
`docs/benchmark_ocr.md` trước khi thay đổi model OCR.
