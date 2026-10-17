# Optimization v3 — Phase 1: Dependency Split

## Mục tiêu

Tách dependency theo trách nhiệm mà không đổi hành vi runtime hiện tại. Core
production không còn cài công cụ lint/test; local PaddleOCR vẫn được giữ tạm
thời cho đến khi OCR service và remote client hoàn tất.

## Thay đổi

| File | Trách nhiệm |
| --- | --- |
| `requirements-core.txt` | FastAPI, LangGraph, PDF processing, Chroma và HTTP client dùng ở runtime. |
| `ocr/requirements-ocr.txt` | PaddlePaddle và PaddleOCR dùng cho OCR cục bộ trong giai đoạn chuyển tiếp. |
| `requirements-dev.txt` | Ruff, pytest và pytest-asyncio; không được cài vào production image. |
| `requirements.txt` | Entry point tương thích cho developer, bao gồm cả ba nhóm. |

`Dockerfile` hiện chỉ cài `requirements-core.txt`; image OCR cài
`ocr/requirements-ocr-service.txt`.
Vì vậy image production vẫn có đúng runtime OCR cũ nhưng không mang theo test
và lint tooling.

## Quyết định giữ nguyên

- `httpx` thuộc core runtime, không phải dev dependency.
- Tesseract OS package vẫn ở Docker image vì parser scan-PDF còn dùng nó.
- Không gỡ PaddleOCR/PaddlePaddle trong phase này để tránh thay đổi hành vi khi
  chưa có remote OCR client.
- Không bổ sung Jinja2.

## Kiểm chứng

1. `requirements.txt` vẫn cài đủ dependency cho developer.
2. Docker build cài core và OCR runtime, không cài pytest/ruff.
3. Các phase tiếp theo sẽ chuyển Docker core sang chỉ `requirements-core.txt`
   sau khi mọi callsite OCR đã dùng service nội bộ.
