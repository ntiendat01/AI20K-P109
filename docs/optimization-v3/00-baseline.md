# Optimization v3 — Phase 0: Baseline

## Mục tiêu

Thiết lập trạng thái có thể đối chiếu trước khi tách OCR, dependency và cấu trúc
module. Phase này không thay đổi hành vi runtime.

## Phạm vi đã chốt

- Core API sẽ tách OCR runtime sang service nội bộ qua HTTP/REST.
- Jinja2 nằm ngoài phạm vi và không được thêm vào dependency trực tiếp.
- `models_v1` không phải quick win để xóa: việc hợp nhất chỉ bắt đầu sau khi có
  inventory import, compatibility mapping và regression test.

> Trạng thái lịch sử: package này đã được chuyển thành `src/models/agent` trong
> phase model consolidation; xem `06-model-migration-inventory.md`.

## Baseline quan sát được

| Hạng mục | Kết quả | Ghi chú |
| --- | --- | --- |
| OCR agent runtime | PaddleOCR cục bộ, `PP-OCRv3` | `PaddleOCRHostedClient` khởi tạo engine cục bộ. |
| OCR parser fallback | Tesseract | Dùng cho PDF scan trong luồng parser. |
| OCR benchmark | 19 tài liệu; accuracy tổng 87,58% | Exact-match trường số là 79,19%. |
| `models_v1` | Đang được import rộng rãi | Không được xóa trước khi migration hoàn tất. |
| Test suite trong `.venv` | 234 passed, 57 failed | Cần ổn định suite trước khi dùng làm regression gate. |
| Docker image size | Chưa đo được tại máy hiện tại | Docker daemon không truy cập được trong môi trường này. |

## Cách đo tái lập trong CI hoặc máy có Docker

```powershell
docker compose build
docker image inspect backend:latest --format '{{.Size}}'
docker image history backend:latest
docker compose up --wait
docker compose down --volumes
```

Kết quả phải ghi rõ platform, image digest, kích thước uncompressed và compressed,
thời gian build, thời gian readiness, RSS đỉnh của core/OCR và phiên bản model OCR.

## Cổng nghiệm thu đề xuất

1. Core image dưới 1.000 MB uncompressed trên `linux/amd64`; mục tiêu là 800 MiB.
2. Bộ benchmark OCR không giảm bất kỳ chỉ số hiện tại nào; mục tiêu độc lập là
   exact-match trường số tối thiểu 80%.
3. Test suite liên quan phải xanh với telemetry tắt và không cần truy cập Internet.
4. OCR outage trả lỗi có thể xử lý, không tạo extraction rỗng.
5. Rollback từ OCR remote về image cũ được kiểm chứng trước khi gỡ OCR runtime
   khỏi core.

## Quyết định triển khai

Triển khai theo lát cắt: dependency split → OCR contract/service → remote client
và shadow mode → cutover → schema/model migration → modularization. Không gộp các
thay đổi đó thành một PR duy nhất.
