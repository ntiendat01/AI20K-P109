# Routing và topology triển khai

## Topology

```text
Client
  │
  ▼
Nginx / frontend container :80
  ├─ /, /dashboard, /requests, /purchase-requests/* → React SPA
  ├─ /assets/*                                    → Vite static assets
  ├─ /healthz                                     → Nginx health
  └─ /api/*                                       → backend:8000 (FastAPI)
                                                        │
                           ┌────────────────────────────┼──────────────┐
                           ▼                            ▼              ▼
                      redis:6379                    ocr:8080       data volume
```

Redis, OCR và backend không publish cổng ra host trong Compose. Chỉ Nginx
publish cổng `80`.

## Route frontend

| Route | Vai trò |
| --- | --- |
| `/login` | Công khai |
| `/dashboard` | Buyer, Manager |
| `/requests` | Buyer, Manager |
| `/purchase-requests/new` | Buyer |
| `/purchase-requests/:id` | Buyer |
| `/purchase-requests/:id/quotations` | Buyer |
| `/purchase-requests/:id/comparison` | Buyer, Manager |
| `/purchase-orders` | Buyer, Manager |
| `/purchase-orders/:id` | Buyer, Manager |

## Route backend

Nginx dùng `proxy_pass http://backend:8000` và không rewrite URI. Do đó:

- `<url>/api/v1/auth/login` tới FastAPI `/api/v1/auth/login`.
- `<url>/api/v1/prs` tới FastAPI `/api/v1/prs`.
- `<url>/api/prs` tới các endpoint compatibility đang dùng prefix `/api`.
- `<url>/api/health` tới health API công khai.

Nginx fallback mọi browser route không phải `/api/` hoặc `/assets/` về
`index.html`, nên refresh trực tiếp một URL SPA vẫn hoạt động.
