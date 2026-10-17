# Những phần đã triển khai

## Ràng buộc triển khai

- Frontend được chuyển hoàn toàn sang React; không render giao diện bằng
  Jinja2 hoặc template phía server.
- Quá trình triển khai không dùng workflow `bmad-build`.

## Nền tảng React

- React 19, TypeScript strict, Vite và React Router.
- API client dùng `fetch`, bearer token và chuẩn hóa lỗi HTTP/validation.
- `AuthProvider` khôi phục phiên bằng `/api/v1/auth/session`, đăng nhập và đăng
  xuất; giữ tương thích khóa `localStorage` cũ.
- Browser routes có protected layout, route guard theo vai trò và chuyển đổi
  bookmark hash cũ.
- Icon SVG được render bằng React; dữ liệu API được JSX escape mặc định. Không
  còn `innerHTML`, `insertAdjacentHTML` hay query DOM để dựng giao diện.

## Workflow nghiệp vụ

- Đăng nhập bằng tài khoản thật hoặc điền nhanh tài khoản demo.
- Dashboard buyer/manager, tìm kiếm, lọc, phân trang và thao tác danh sách PR.
- Tạo PR nhiều dòng hàng, nhập nhanh ngân sách/hạn giao, bulk import CSV, lưu
  nháp, sửa và xóa PR.
- Upload song song tối đa 5 PDF, trạng thái từng file, xóa từng hoặc toàn bộ
  báo giá.
- Rà soát báo giá, mở file gốc có overlay vùng trích xuất, sửa dòng hàng,
  thông tin thương mại, VAT/phí/giao hàng/bảo hành, xác nhận và mở lại.
- Bảng fuzzy matching, lọc nhà cung cấp, tìm mặt hàng, gộp/tách/ghép thủ công.
- Khởi chạy và poll phân tích có cleanup khi unmount; hiển thị đề xuất đã kiểm
  chứng, xếp hạng/TCO, tải evidence và gửi manager phê duyệt.
- Manager phê duyệt/từ chối với idempotency payload; điều hướng tới PO nháp.
- Danh sách PO, chi tiết PO, in/lưu PDF qua chức năng trình duyệt.

## Mã legacy đã loại bỏ

Toàn bộ entry point và module JavaScript thuần trong `frontend/app.js`,
`frontend/core`, `frontend/config`, `frontend/features` và `frontend/utils` đã
được xóa sau khi React build thành công. Lịch sử Git vẫn khôi phục được chúng.

## Những thay đổi backend tối thiểu

- FastAPI không còn mount hoặc phục vụ `/ui/`.
- Backend có health endpoint công khai nội bộ tại `/api/health`.
- Cấu hình nhận `REDIS_URL`; Redis chưa thay thế repository SQLite hay cache
  nghiệp vụ trong phạm vi migration frontend này.

## Hạ tầng chạy production

- Container `frontend` build Vite bằng Node rồi phục vụ thư mục `dist` bằng
  Nginx.
- Nginx là điểm vào duy nhất ở cổng 80: browser route và asset đi vào
  frontend, còn `/api/` được giữ nguyên URI và proxy tới `backend:8000`.
- Container `backend`, `redis` và `ocr` chỉ mở cổng trong mạng Compose; backend
  nhận `REDIS_URL=redis://redis:6379/0` và chờ Redis/OCR healthy trước khi chạy.
- Redis bật AOF và dùng named volume `redis-data` để giữ dữ liệu qua lần khởi
  động lại container.
