# Chuyển frontend sang React

## Trạng thái

**Đã triển khai — React production build và topology Nginx đã được kiểm chứng.**

Tài liệu này lưu phương án gốc và quyết định migration. Kết quả thực hiện chi
tiết nằm tại `IMPLEMENTATION.md`; routing và triển khai nằm tại `ROUTING.md`;
kết quả kiểm tra nằm tại `VERIFICATION.md`.

## Mục tiêu

- Chuyển toàn bộ UI sang React 19 + TypeScript + Vite, phục vụ tại `/`.
- Giữ nguyên API FastAPI, API contract, xác thực bearer token và dữ liệu trong
  `localStorage`; chỉ tách trách nhiệm phục vụ frontend khỏi backend.
- Giữ nguyên hành vi nghiệp vụ: đăng nhập, phân quyền theo vai trò, PR, báo
  giá, fuzzy matching, phân tích bất đồng bộ, phê duyệt và PO.
- Tiếp tục dùng các token giao diện, font Manrope và quy tắc responsive trong
  `docs/STYLE_GUIDE.md`.

## Khảo sát đã hoàn thành

| Khu vực | Hiện trạng | Hệ quả khi chuyển đổi |
| --- | --- | --- |
| Khởi động | `frontend/index.html` tải `app.js` trực tiếp | Thay entry point bằng `src/main.tsx` do Vite build. |
| Điều hướng | Hash router tự viết trong `frontend/core/router.js` | Dùng React Router với browser routes; tự chuyển URL hash cũ sang route mới. |
| Phiên | `localStorage`, `restoreSession()` và API `/auth/session` | Đưa vào `AuthProvider`/`useAuth`; giữ khóa storage và quy trình xác thực. |
| Gọi API | `requestApi()` dùng `fetch` và bearer token | Tách thành typed API client, vẫn gọi đúng `/api/v1`. |
| Giao diện | Các feature render bằng `innerHTML` rồi tự gắn listener | Thay bằng React component, state và effect; loại bỏ thao tác DOM thủ công. |
| Phục vụ production | FastAPI từng mount thư mục `frontend` tại `/ui/` | Nginx phục vụ Vite artifact tại `/`; `/api/` được proxy sang FastAPI. |
| Docker | Image backend từng copy toàn bộ `frontend/` | Build frontend bằng Node và chỉ copy `dist` sang image Nginx riêng; image backend chỉ chứa API. |

## Phạm vi feature phải giữ nguyên

| Feature hiện hữu | Điểm vào JavaScript hiện tại | Đích React |
| --- | --- | --- |
| Đăng nhập/đăng xuất/khôi phục phiên | `features/auth/auth.js` | `features/auth/` + `AuthProvider` |
| Layout, menu, phân quyền | `core/router.js` | `layouts/AppShell.tsx`, route guard |
| Dashboard và danh sách PR | `features/workspace/workspace.js` | `features/workspace/` |
| Tạo, sửa, chi tiết PR | `features/purchase-request/purchase-request.js` | `features/purchase-request/` |
| Báo giá, upload và fuzzy matching | `features/quotations/` | `features/quotations/` |
| Phân tích, polling, evidence và review | `features/comparison/comparison.js` | `features/comparison/` |
| Danh sách phê duyệt/lịch sử | `features/approvals/`, `features/history/` | `features/approvals/`, `features/history/` |
| Chi tiết PO | `features/purchase-order/purchase-order.js` | `features/purchase-order/` |

## Phương án kỹ thuật

```text
Browser
  └─ /  →  Nginx → React SPA (Vite artifact)
                  ├─ React Router (browser routes)
                  ├─ AuthProvider / FlashProvider
                  ├─ Typed API client (fetch)
                  ├─ Feature components
                  └─ Existing styles.css and SVG icon set
                         │
                         └─ /api, /api/v1  →  FastAPI (không đổi contract)
```

### Quyết định chính

1. **Vite thay vì Next.js.** Backend đã là FastAPI và UI là ứng dụng nội bộ
   đăng nhập; không có nhu cầu SSR/SEO. Vite giữ deployment đơn giản, build
   nhanh và không đưa Node server vào production.
2. **TypeScript strict.** API trả nhiều cấu trúc dữ liệu nghiệp vụ; type cho
   request/response giúp phát hiện sai contract tại build time.
3. **React Router `BrowserRouter`.** Nginx trả `index.html` cho mọi route SPA;
   một compatibility redirect chuyển bookmark `#/…` cũ sang URL mới.
4. **React state + custom hooks trước, không thêm Redux/Zustand.** State chung
   duy nhất là phiên/flash; state màn hình nằm trong feature. Chỉ đánh giá
   TanStack Query sau khi conversion chạy ổn định.
5. **Giữ stylesheet trung tâm ở giai đoạn một.** CSS đã có token và quy chuẩn
   rõ. Chuyển đổi component trước, tách CSS theo component sau nếu cần.
6. **Không dùng `dangerouslySetInnerHTML` cho dữ liệu API.** JSX tự escape dữ
   liệu; icon SVG sẽ được chuyển thành React component an toàn.

## Cấu trúc đích

```text
frontend/
  Dockerfile
  nginx.conf
  index.html
  package.json
  package-lock.json
  tsconfig.json
  vite.config.ts
  styles.css
  src/
    main.tsx
    App.tsx
    AppShell.tsx
    AuthProvider.tsx
    LoginPage.tsx
    api.ts
    config.ts
    routing.ts
    session.ts
    types.ts
    ui.tsx
    utils.ts
    features/
      workspace.tsx
      purchaseRequests.tsx
      quotations.tsx
      SourceReview.tsx
      comparison.tsx
      purchaseOrders.tsx
    test/
```

## Kế hoạch thực hiện — từng bước nhỏ

| Bước | Thay đổi | Kiểm chứng | Commit dự kiến |
| --- | --- | --- | --- |
| 1 | Khởi tạo Vite/React/TypeScript, cấu hình build tại `/`, giữ stylesheet và assets | `npm run build` | `build(frontend): bootstrap React application` |
| 2 | Tạo API client typed, session/auth provider, flash state, test API logic | unit test + type check | `feat(frontend): add React session and API foundation` |
| 3 | Chuyển app shell, sidebar, browser routes, compatibility redirect, role guard và login | smoke test route/auth và component test | `feat(frontend): migrate navigation and authentication` |
| 4 | Chuyển workspace và purchase request | test create/edit/list/detail PR | `feat(frontend): migrate purchase request workflow` |
| 5 | Chuyển quotation upload, source review và fuzzy matching | test upload/match interaction | `feat(frontend): migrate quotation workflow` |
| 6 | Chuyển comparison, polling có cleanup, approval/history/PO | test polling, review, PO navigation | `feat(frontend): migrate analysis and approval workflow` |
| 7 | Đổi Docker/Nginx sang phục vụ `dist`, bỏ static mount và module JS cũ | build image, test `/`, `/api/`, `make check` | `build(frontend): serve React production bundle` |
| 8 | Regression, accessibility và cập nhật tài liệu | `npm run test`, `npm run build`, `make check` | `docs(frontend): document React migration` |

## File dự kiến thay đổi

### Tạo mới

- `frontend/package.json`, lockfile, `tsconfig.json`, `vite.config.ts` và cấu
  hình test.
- Toàn bộ `frontend/src/` theo cấu trúc ở trên.
- Test cho API client, auth, router, polling analysis và các component/hook có
  logic nghiệp vụ.
- Tài liệu implementation, decision log và checklist regression tại
  `docs/convert-frontend/`.

### Sửa

- `frontend/index.html`: entry point của Vite.
- `frontend/styles.css`: chỉ sửa đường dẫn asset/class thật sự cần cho JSX.
- `src/main.py`: bỏ static mount frontend; chỉ cung cấp backend/API và health.
- `frontend/Dockerfile`: multi-stage build Node → Nginx runtime.
- `Dockerfile`: bỏ frontend khỏi image backend.
- `docker-compose.yml`: chạy riêng Nginx/frontend, FastAPI/backend, Redis và OCR.

### Xóa sau khi nghiệm thu toàn bộ

- `frontend/app.js`, `frontend/config/`, `frontend/core/`,
  `frontend/features/` và `frontend/utils/` phiên bản JavaScript cũ.

Không xóa mã legacy trước khi UI React pass đầy đủ regression.

## Dependency dự kiến cần chấp thuận

- Runtime: `react`, `react-dom`, `react-router-dom`.
- Development: `vite`, `typescript`, `@vitejs/plugin-react`, `vitest`,
  `@testing-library/react`, `@testing-library/user-event`, `jsdom`, các type
  package tương ứng.

Không thêm state manager, UI kit hay thư viện gọi HTTP ở lần migration đầu.

## Rủi ro và biện pháp kiểm soát

| Rủi ro | Kiểm soát |
| --- | --- |
| Lệch API contract | Gắn type theo response thực tế, test API client và giữ endpoint không đổi. |
| Polling vẫn chạy sau khi rời màn hình | Dùng `useEffect` cleanup/`AbortController`. |
| Mất dữ liệu form khi re-render | Controlled state hoặc `react-hook-form` chỉ nếu cần; test create/edit PR. |
| Vỡ deep-link | Nginx fallback về `index.html`; redirect tự động map hash route cũ. |
| Sai phân quyền UI | Route guard dựa trên `roleConfig` hiện hữu, test buyer và manager. |
| Asset path sai | Thiết lập Vite `base: '/'`, build trong Docker và kiểm tra Nginx. |
| Docker image nặng/chậm | Multi-stage build và chỉ sao chép `dist` vào image Nginx runtime. |

## Tiêu chí nghiệm thu

- Route mới hoạt động khi deep-link; URL hash cũ được chuyển sang route tương ứng.
- Buyer và manager chỉ thấy/thao tác được đúng phần được phân quyền.
- Luồng PR → báo giá → fuzzy match → phân tích/polling → review → PO hoạt
  động với API hiện tại, không đổi endpoint hay payload.
- Không còn render template UI qua `innerHTML`; dữ liệu backend không đi qua
  HTML string interpolation.
- `npm run typecheck`, `npm run test`, `npm run build` và `make check` pass.
- Image Docker production build được; Nginx phục vụ `/`, health tại `/healthz`
  và proxy backend dưới `/api/`.

## Ngoài phạm vi

- Đổi backend API, schema, database hoặc logic LangGraph.
- Thay đổi thiết kế visual/UX ngoài các sửa cần thiết để giữ giao diện tương
  đương.
- SSR, SEO, PWA, Redux/Zustand hoặc thay toàn bộ CSS bằng một UI kit.

