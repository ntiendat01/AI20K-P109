# Spec 4.3 — Upload & trích xuất báo giá

**P-109 · MVP Cơ bản**

## Mục tiêu

Cho phép upload báo giá từ nhiều NCC cho cùng một PR, agent tự động trích xuất số liệu.

## Phạm vi

- Trong phạm vi: upload PDF (+ tối thiểu 1 định dạng khác: email/txt), OCR/parser trích các trường chính, màn hình xác nhận/sửa tay, tối đa 5 file cùng lúc và có thể kéo thả.
- Ngoài phạm vi: tự động lấy báo giá qua hộp thư (thuộc phần Nâng cao — agent tự soạn email hỏi báo giá).

## Input / Output

- Input: file PDF/email báo giá, gắn với 1 PR và 1 NCC.
- Output: bản ghi `quotations` + `quotation_items` đã trích xuất (chưa chuẩn hóa).

## Yêu cầu chi tiết

- Upload nhiều file cho cùng 1 PR, mỗi file gắn với 1 NCC, không cần nhập tên NCC.
- Dùng OCR/parser bảng (Document AI hoặc Camelot) trích: tên NCC, tên/mã sản phẩm, đơn giá, số lượng, thành tiền, thời gian giao, điều khoản thanh toán.( nếu không được thì dùng thư viện PDFplumber để trích xuất được các trường dữ liệu có trong PDF).
- Màn hình hiển thị bản trích xuất dạng bảng để nhân viên đối chiếu với file gốc và sửa tay trước khi xác nhận — **bắt buộc**, vì đây là ràng buộc độ chính xác số liệu tài chính của đề bài. Khi mà trích xuất được dữ liệu xong thì có thể hiển thị được các bảng dữ liệu tương ứng theo ví dụ sau 
| Sản phẩm                 | Supplier A | Supplier B | Supplier C | Supplier D |
| ------------------------ | ---------: | ---------: | ---------: | ---------: |
| Dell Latitude 5450       |      24.5M |      23.9M |      25.2M |     24.75M |
| Dell P2425H              |       5.2M |      4.95M |       5.1M |      5.05M |
| Logitech MK850           |      1.75M |      1.68M |      1.82M |     1.725M |
| Dell WD19S               |       4.2M |      3.99M |          — |       4.1M |
| **HP LaserJet M404**     |          — |          — |   **8.5M** |          — |
| **Cisco Switch 24-port** |          — |  **12.8M** |          — |  **13.1M** |
- Mỗi quotation có trạng thái: Chưa xác nhận / Đã xác nhận; chỉ quotation đã xác nhận mới được đưa vào bước so sánh.

## Liên quan

- Data: bảng `quotations`, `quotation_items`.
- API: `POST /prs/{id}/quotations`.

## Tiêu chí hoàn thành

- Upload thành công, agent trả về bản trích xuất trong thời gian chấp nhận được.
- Các trường chính trích đúng trên bộ dữ liệu test synthetic.
- Sửa tay được, và bản đã sửa (không phải bản OCR gốc) được dùng cho bước sau khi đã xác nhận.
