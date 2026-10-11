# Spec 4.5 — So sánh & đề xuất NCC

**P-109 · MVP Cơ bản**

## Mục tiêu

Hiển thị bảng so sánh song song các NCC và sinh một đề xuất NCC kèm giải thích.

## Phạm vi

- Trong phạm vi: so sánh theo giá – chất lượng – thời gian giao, kiểm tra chính sách mua sắm bằng RAG, sinh 1 đề xuất kèm lý do bằng văn bản.
- Ngoài phạm vi: tính TCO chi tiết, chấm điểm NCC tự động theo lịch sử vi phạm (thuộc phần Nâng cao).

## Input / Output

- Input: `quotation_items` đã chuẩn hóa (kết quả bước 4.4) + hồ sơ NCC trong vector DB + tài liệu chính sách mua sắm.
- Output: bảng so sánh trên frontend + 1 đề xuất NCC kèm đoạn giải thích.

## Yêu cầu chi tiết

- Bảng so sánh: mỗi cột là 1 NCC, mỗi hàng là 1 tiêu chí (giá, chất lượng theo hồ sơ, thời gian giao).
- Agent truy vấn RAG trên chính sách mua sắm để kiểm tra NCC có hợp lệ (vd nằm trong danh sách được duyệt) hay không.
- Sinh đoạn giải thích ngắn gọn nêu rõ căn cứ chọn NCC đề xuất, dựa trên số liệu và chính sách.
- Log lại các bước xử lý của agent để có thể truy vết khi cần (đảm bảo minh bạch).

## Liên quan

- Data: bảng `suppliers`, vector DB hồ sơ NCC + tài liệu chính sách.
- API: `GET /prs/{id}/comparison`.

## Tiêu chí hoàn thành

- [ ] Bảng so sánh hiển thị đủ 3 tiêu chí cho tất cả NCC đã báo giá cho PR đó.
- [ ] Đề xuất luôn kèm giải thích, không có trường hợp hiển thị đề xuất trống.
- [ ] NCC không hợp lệ theo chính sách bị cảnh báo hoặc loại khỏi đề xuất.