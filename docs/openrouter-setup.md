# Setup OpenRouter – Qwen3.8 27B free

Code hỗ trợ OpenRouter cho cả AI extraction PDF và decision trong luồng FE → BE → Agent. Không cần thêm dependency. API key chỉ đọc từ cấu hình server, không đi qua frontend. Chưa gọi OpenRouter thật trong lần setup này; test dùng HTTP fixture, bạn tự điền key sau.

## Cấu hình

Thêm hoặc cập nhật các dòng sau trong `.env` ở thư mục gốc; điền key vào dòng trống:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL_NAME=qwen/qwen3.8-27b:free
OPENROUTER_TIMEOUT_SECONDS=300
OPENROUTER_MAX_TOKENS=8192
OPENROUTER_REASONING_ENABLED=false
```

Model ID được xác minh ngày 03/10/2026 trên [trang Qwen3.8 27B free của OpenRouter](https://openrouter.ai/qwen/qwen3.8-27b:free). Hậu tố `:free` chọn bản miễn phí. Code không tự đổi sang model trả phí hoặc provider khác khi thiếu key/lỗi request. Bạn có thể giữ các key Groq/Qwen/Gemini cũ: `LLM_PROVIDER=openrouter` buộc extraction và decision dùng OpenRouter.

`OPENROUTER_SITE_URL` và `OPENROUTER_APP_NAME` là tùy chọn cho attribution headers; app name mặc định `Procura`. Request dùng Chat Completions với JSON mode và mặc định tắt reasoning để dành output cho JSON. JSON vẫn phải qua schema/evidence evaluation trước khi duyệt. [API và headers](https://openrouter.ai/docs/quickstart), [reasoning](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

## Chạy

Restart BE sau khi lưu `.env` vì Settings được cache:

```sh
.venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000/ui/`. Khi upload báo giá PDF, chọn **Đọc và trích xuất bằng AI (PDF)**; nếu chọn parser thì extraction không gọi model. Buyer đối chiếu/xác nhận dữ liệu rồi bấm **Phân tích bằng Agent**. Xem các bước Buyer/Manager và PO trong [runbook](end-to-end-runbook.md).

Có thể kiểm tra bằng dữ liệu PDF ẩn danh trước khi thử UI:

```sh
.venv/bin/python -m scripts.smoke_procurement_live --provider openrouter --output /private/tmp/procura-live-openrouter.json
```

Lệnh này gọi model thật ở extraction và decision; chỉ dùng stores tạm. Nó mô phỏng Buyer xác nhận và Manager approve, kiểm TCO/PO theo đáp án tính tay, retry không sinh PO trùng. Chỉ `result=passed` mới là pass; `not_ready` có diagnostics trong file report, không coi là đã chạy xong.

## Khi chưa chạy được

- Thiếu `OPENROUTER_API_KEY`: client báo cấu hình thiếu, không dùng key Groq/OpenAI thay thế.
- HTTP 401: kiểm tra key OpenRouter và restart BE; key provider khác không dùng được ở endpoint này.
- HTTP 429: model free có rate limit; xem quota/tình trạng trên OpenRouter và thử lại sau. [Rate limits](https://openrouter.ai/docs/api/reference/limits).
- Model/provider không sẵn sàng hoặc trả JSON sai: luồng dừng ở technical_failure/needs_input/repairable và không tạo PO. Kiểm tra model ID giữ nguyên `:free`; nếu output bị cắt có thể tăng `OPENROUTER_MAX_TOKENS` hoặc timeout rồi restart.
- PDF scan vẫn cần cấu hình PaddleOCR hosted; PDF có text dùng PyMuPDF cục bộ. OpenRouter hiện nhận OCR text, không tự thay OCR.

Không sửa `.env` tự động và không chạy lệnh Git trong task setup này.
