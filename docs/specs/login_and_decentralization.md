# Spec 4.1 — Đăng nhập & phân quyền

**P-109 · MVP Cơ bản**

## Mục tiêu

Cho phép người dùng đăng nhập và giới hạn quyền truy cập theo 1 trong 2 vai trò cố định.

## Phạm vi

- Trong phạm vi: đăng nhập email/mật khẩu, 2 vai trò cố định (Nhân viên mua sắm, Quản lý duyệt).
- Ngoài phạm vi: SSO, tự đăng ký, phân quyền nhiều cấp theo hạn mức (thuộc phần Nâng cao).

## Input / Output

- Input: email + mật khẩu.
- Output: token/session kèm vai trò người dùng.

## Yêu cầu chi tiết

- Form đăng nhập, thông báo lỗi rõ ràng khi sai tài khoản.
- Backend xác thực và trả về vai trò.
- Route guard ở frontend: Nhân viên mua sắm chỉ vào được trang tạo PR/upload/so sánh; Quản lý chỉ vào được trang duyệt.
- Có đăng xuất, session hết hạn sau một khoảng thời gian.

## Liên quan

- Data: bảng `users` (id, tên, email, vai trò).
- API: `POST /auth/login`.

## Tiêu chí hoàn thành

- Đăng nhập đúng/sai tài khoản cho kết quả đúng.
- Tài khoản test của từng vai trò chỉ thấy đúng menu/chức năng của mình.
- Truy cập trái phép vào trang của vai trò khác bị chặn.
