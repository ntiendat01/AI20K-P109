# Specs 4.2 — Tạo & quản lý PR (Đề nghị mua hàng)

**P-109 · MVP Cơ bản**

## Mục tiêu

Nhân viên mua sắm tạo PR và theo dõi PR qua các trạng thái xử lý.

## Phạm vi

- Trong phạm vi: form tạo PR, danh sách PR lọc theo trạng thái, xem chi tiết, tự chuyển trạng thái theo luồng.
- Ngoài phạm vi: sửa PR sau khi đã có báo giá, xóa PR.

## Input / Output

- Input: mã PR, người tạo, danh mục hàng hóa/dịch vụ, số lượng, ngân sách dự kiến, hạn giao.
- Output: PR được lưu, hiển thị trong danh sách theo đúng trạng thái.

## Yêu cầu chi tiết

- Form nhập PR, validate cơ bản (số lượng > 0, ngân sách > 0, hạn giao trong tương lai).
- Danh sách PR lọc theo trạng thái: Nháp / Chờ báo giá / Đang so sánh / Chờ duyệt / Đã duyệt / Từ chối.
- Trang chi tiết PR hiển thị thông tin + trạng thái + các báo giá đã đính kèm (khi có).
- Trạng thái tự chuyển: Nháp → Chờ báo giá (khi lưu) → Đang so sánh (khi có ≥1 báo giá) → Chờ duyệt (khi nhân viên gửi duyệt) → Đã duyệt/Từ chối.

## Liên quan

- Data: bảng `purchase_requests`.
- API: `GET /prs`, `POST /prs`.

## Tiêu chí hoàn thành

- Tạo PR thành công, xuất hiện đúng trạng thái ban đầu.
- Danh sách lọc đúng theo từng trạng thái.
- Trạng thái tự chuyển đúng khi có báo giá / khi gửi duyệt.
