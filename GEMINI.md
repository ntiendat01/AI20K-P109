# Đặc tả lập plan

Chỉ ghi `tasks/{TASK_ID}.plan.md`. Không sửa `src/`, `tests/`.

## Đầu vào (đọc theo thứ tự, không đọc thêm)
1. ARCHITECTURE.md
2. tasks/{TASK_ID}.md
3. Chỉ các file trong mục "Tài liệu liên quan" của task

## Cấu trúc plan (bắt buộc đủ 6 mục)
### 1. Tóm tắt
Task làm gì, US-ID nào, 2-3 câu.
### 2. Phạm vi file
| File | Hành động | Ghi chú |
Kèm danh sách **KHÔNG được đụng**.
### 3. Các bước
Mỗi bước: mục tiêu, file sửa, test cần viết, lệnh kiểm chứng, commit message.
Mỗi bước ≤ 1 commit.
### 4. Thay đổi contract/schema
Không có, hoặc mô tả field cụ thể. Đánh dấu **CẦN DUYỆT**.
### 5. Rủi ro và giả định
### 6. Câu hỏi cần quyết
Chỗ nào spec thiếu hoặc mơ hồ thì ghi ở đây. Không tự chọn.

## Quy tắc
- Plan phải tự đủ: người đọc không thấy cuộc chat này.
- Không nêu đường dẫn, tên hàm chưa xác nhận trong repo. Chưa chắc thì tìm hoặc hỏi.
- Xong thì dừng, chờ duyệt.