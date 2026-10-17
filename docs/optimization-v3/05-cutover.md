# Optimization v3 — Phase 5: Core Cutover

## Mục tiêu

Chuyển production Compose sang OCR service và bỏ OCR runtime khỏi core image.
Local mode vẫn có trong source/developer install để hỗ trợ rollback và so sánh,
nhưng Docker core production không còn mang Paddle hoặc Tesseract.

## Thay đổi

- Backend Compose đặt `OCR_MODE=remote`, trỏ `OCR_SERVICE_BASE_URL` tới service
  `ocr` và chờ OCR healthcheck trước khi khởi động.
- Core `Dockerfile` chỉ cài `requirements-core.txt`; đã bỏ Paddle dependency và
  OS packages Tesseract.
- `src/extraction/ocr_extractor.py` chuyển parser scan-PDF sang cùng remote
  service khi `OCR_MODE=remote`.
- Shadow mode cho parser vẫn trả kết quả Tesseract local và chỉ so sánh remote.

## Rollback

Đặt `OCR_MODE=local` hoặc `OCR_MODE=shadow` trong môi trường có local OCR
runtime. Với production image mới, rollback an toàn là triển khai lại image
core trước cutover vì image mới cố ý không chứa local Paddle/Tesseract.

## Kiểm chứng cần chạy trên Docker-enabled CI

```powershell
docker compose build
docker compose up --wait
# chạy smoke test PDF text, scan và mixed PDF
docker compose down --volumes
```

Máy hiện tại không truy cập được Docker daemon nên không thể xác nhận kích thước
image hay compose smoke test ở đây. Unit test xác nhận parser gọi remote client
khi remote mode được bật.
