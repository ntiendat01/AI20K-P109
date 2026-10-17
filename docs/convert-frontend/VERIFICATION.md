# Kết quả kiểm chứng

## Frontend

| Kiểm tra | Kết quả |
| --- | --- |
| `npm run typecheck` | Pass |
| `npm run test` | Pass, 4 files / 8 tests |
| `npm run build` | Pass, Vite tạo production artifact |
| Smoke GET `/` qua Vite | HTTP 200, React entry được trả về |
| Smoke POST `/api/v1/auth/login` qua Vite proxy | HTTP 200, trả role `procurement` và token |
| `docker compose config --quiet` | Pass |
| `docker compose build frontend` | Pass |
| `nginx -t` trong image với hostname backend giả lập | Pass |
| Smoke trực tiếp trong container Nginx | `/healthz` trả `ok`; `/` trả React `index.html` |

Production bundle tại lần kiểm tra: JavaScript khoảng 353 KB (gzip khoảng
107 KB), CSS khoảng 90 KB (gzip khoảng 18 KB).

## Backend

- Test tập trung cho auth/routing mới: 12/12 pass trong `test_auth.py` và
  `test_routes.py`.
- Ruff cho các file Python thay đổi: pass.
- Full suite: 244 pass, 57 fail. Test `/ui/` thuộc kiến trúc cũ đã được cập
  nhật sang kỳ vọng backend không phục vụ asset legacy. Các lỗi còn lại
  nằm ở fixtures/schema và workflow nghiệp vụ hiện hữu (ví dụ payload PR cũ
  thiếu field mới), không phát sinh từ React/Nginx migration.
- `make check` chưa thể pass vì toàn repo hiện có 8 file không đạt `ruff
  format --check` và các lỗi backend nói trên. Không tự format/sửa các file
  ngoài phạm vi migration.
