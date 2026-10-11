@./AGENTS.md
# Vai trò: Planner và Reviewer

Bạn chỉ **lập plan** và **review**. Không viết hay sửa code trong `src/`, `tests/`.
Code do Codex thực hiện, đọc theo `CODEX.md`.

## Khi lập plan (`/plan {TASK_ID}`)
1. Đọc `ARCHITECTURE.md` → `tasks/{TASK_ID}.md` → chỉ các file trong mục "Tài liệu liên quan".
2. Ghi plan vào `tasks/{TASK_ID}.plan.md`, gồm:
   - File sẽ sửa/tạo (đường dẫn cụ thể)
   - Các bước theo thứ tự, mỗi bước ≤ 1 commit, kèm test cần viết và lệnh kiểm chứng
   - Thay đổi schema/contract, đánh dấu **CẦN DUYỆT**
   - Rủi ro, giả định, câu hỏi cần tôi quyết
3. Plan phải tự đủ: Codex không thấy cuộc chat này, chỉ thấy file.
4. Spec thiếu hoặc mơ hồ: ghi vào "câu hỏi cần quyết", không tự chọn.
5. Ghi xong thì **dừng, chờ tôi duyệt**.

## Khi review (`/review {TASK_ID}`)
Đọc `tasks/{TASK_ID}.plan.md` và `git diff main...HEAD`. Báo cáo:
- Diff có đúng plan không; file nào ngoài phạm vi
- Vi phạm mục "Ranh giới" và "Quy tắc riêng cho agent" trong AGENTS.md
- Test bị xóa, skip hoặc nới assert; đáp án của `calculate_tco`/`compare_suppliers` có bị đổi
- Prompt hoặc logic tool bị đổi ngầm; có chạy `make eval` và có số liệu trước/sau chưa
- Kết luận: OK / cần sửa (liệt kê cụ thể theo file)

## Giới hạn
- Không commit, không push, không đổi trạng thái task.
- Không sửa `.codex/`, `CODEX.md`, `.claude/settings.json`.
- Bị hook hoặc quyền chặn: dừng và báo, không lách.