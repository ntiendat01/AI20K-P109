# Spec 4.6 — Duyệt & tạo PO

**P-109 · MVP Cơ bản**

## Mục tiêu

Quản lý xem xét đề xuất của agent và quyết định duyệt; hệ thống sinh PO ở trạng thái nháp.

## Phạm vi

- Trong phạm vi: 1 cấp duyệt duy nhất, sinh PO nháp.
- Ngoài phạm vi: nhiều cấp phê duyệt theo hạn mức, tự động gửi PO cho NCC (thuộc phần Nâng cao).

## Input / Output

- Input: PR ở trạng thái Chờ duyệt + bảng so sánh + đề xuất của agent.
- Output: PO nháp nếu duyệt, hoặc PR quay lại trạng thái Đang so sánh nếu từ chối.

## Yêu cầu chi tiết

- Màn hình duyệt cho Quản lý: xem đầy đủ thông tin PR, bảng so sánh, và giải thích đề xuất.
- Nút Duyệt / Từ chối — thao tác tường minh, bắt buộc con người quyết định (HITL); agent chỉ đề xuất, không tự chọn.
- Khi Duyệt: sinh PO nháp gồm mã PO, NCC được chọn, hạng mục, tổng giá trị, điều khoản; PO ở trạng thái nháp, **không** tự động gửi đi hay đặt hàng.
- Khi Từ chối: PR quay lại trạng thái trước đó, có ghi chú lý do từ chối.

## Liên quan

- Data: bảng `purchase_orders`.
- API: `POST /prs/{id}/approve`, `POST /prs/{id}/po`.

## Tiêu chí hoàn thành

- [ ] Duyệt sinh đúng PO nháp với đầy đủ thông tin.
- [ ] Từ chối không sinh PO, PR quay lại đúng trạng thái kèm lý do.
- [ ] Không có đường nào khiến hệ thống tự tạo PO mà không qua thao tác Duyệt của Quản lý.