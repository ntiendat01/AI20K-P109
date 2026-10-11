# Spec 4.4 — Chuẩn hóa dữ liệu

**P-109 · MVP Cơ bản**

## Mục tiêu

Đưa dữ liệu từ các báo giá khác nhau về cùng một chuẩn để có thể so sánh trực tiếp.

## Phạm vi

- Trong phạm vi: quy đổi đơn vị/tiền tệ, ánh xạ tên mặt hàng tương đương giữa các NCC.
- Ngoài phạm vi: tự học/cải thiện matching theo thời gian bằng ML.

## Input / Output

- Input: `quotation_items` đã xác nhận (kết quả của bước 4.3).
- Output: `quotation_items` với tên hàng chuẩn hóa + đơn giá quy đổi cùng đơn vị/tiền tệ.

## Yêu cầu chi tiết

- Bảng quy đổi đơn vị (vd kg↔g, thùng↔cái) và tỷ giá tiền tệ áp dụng khi báo giá bằng ngoại tệ.
- Luật/thuật toán ánh xạ tên hàng tương đương giữa các NCC (rule-based cho MVP; có thể nâng cấp bằng embedding matching sau).
- Đánh dấu (cảnh báo) các item không ánh xạ được để nhân viên xử lý thủ công, không được bỏ sót âm thầm.

## Liên quan

- Data: `quotation_items` (bổ sung cột tên chuẩn hóa, đơn giá quy đổi).
- API: xử lý nội bộ trong agent pipeline, không cần endpoint riêng ở mức MVP.

## Tiêu chí hoàn thành

- [ ] Các mặt hàng cùng loại từ các NCC khác nhau được gộp đúng vào cùng nhóm so sánh.
- [ ] Đơn giá hiển thị cùng đơn vị và cùng loại tiền tệ.
- [ ] Item không ánh xạ được hiển thị cảnh báo rõ ràng cho nhân viên.