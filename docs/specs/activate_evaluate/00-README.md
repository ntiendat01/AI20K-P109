# Bộ spec phát triển và tối ưu Procurement Agent

15 task, mỗi task một file, tự chứa đủ ngữ cảnh để giao riêng cho agent. Agent **không commit/push**; bạn tự review và push.

## Danh sách và thứ tự

| # | File | Nội dung | Phụ thuộc |
|---|---|---|---|
| 1 | P1-T1-guard-tests.md | Test bảo vệ "raw LLM không tạo được PO" | không |
| 2 | P1-T2-enable-evaluate.md | Bật lại node `evaluate` trong graph | T1 |
| 3 | P1-T3-backend-remove-bypass.md | Backend: bỏ `untrusted_proposal` và nhánh bypass | T2 |
| 4 | P1-T4-frontend-verified-only.md | Frontend: chỉ hiện điều khiển khi có verified review | T3 |
| 5 | P1-T5-e2e-tests.md | Test end-to-end luồng chuẩn | T4 |
| 6 | P2-T1-llm-json-retry.md | Retry/repair khi Decision LLM trả JSON hỏng | T2 |
| 7 | P2-T2-strict-validation.md | Khôi phục strict validation, đánh dấu fallback | T2 |
| 8 | P2-T3-error-states.md | Hoàn thiện `needs_input`/`repairable`/`technical_failure`/Revise/Reject | T3, T4 |
| 9 | P2-T4-proposal-consistency.md | Kiểm tra nhất quán proposal trong `evaluate` | T2 |
| 10 | P2-T5-full-graph-ui.md | Nối nhánh OCR/extraction vào UI (mặc định: bỏ qua) | cần quyết định |
| 11 | P3-T1-async-analysis.md | POST analysis bất đồng bộ (202 + polling) | P1 xong |
| 12 | P3-T2-cache-snapshot.md | Cache theo `snapshot_revision`, cache evidence | T11 |
| 13 | P3-T3-observability.md | Mở rộng `events`, log có cấu trúc | T11 |
| 14 | P3-T4-payload-reduction.md | Giảm payload gửi LLM | P2-T4 |
| 15 | P3-T5-db-consistency.md | Nhất quán giữa hai SQLite | T11 |

Làm theo thứ tự số. P1 nên làm trọn bộ (T1 → T5) rồi mới sang P2. Task trong P2 và P3 có thể làm song song nếu phụ thuộc đã xong.

## Quy trình cho từng task

1. Chạy `git status` đảm bảo working tree sạch (hoặc commit/stash phần dở của bạn trước).
2. Đưa agent file task (và nhớ đã có `_common` ở cuối file).
3. Agent làm xong, báo cáo theo mẫu.
4. Bạn chạy "Checklist tự kiểm tra" trong file task: `git diff --stat`, đọc diff, chạy test.
5. Ổn thì bạn tự `git add`/`commit`/`push`. Chưa ổn thì yêu cầu agent sửa tiếp trong cùng working tree.

Prompt mẫu:

> Đọc file spec đính kèm và thực hiện đúng phạm vi trong đó. Không chạy lệnh git ghi (commit, push, branch, stash, reset). Khi xong, báo cáo theo mục "Quy tắc chung".

## Các quyết định mặc định

Mỗi task có mục "Quyết định" với giá trị mặc định để agent chạy được ngay. Đổi trong file trước khi giao nếu bạn muốn khác.

| Quyết định | Mặc định | Task |
|---|---|---|
| Run cũ `untrusted_proposal` khi migrate | Đánh dấu `stale`; PR đang `pending_approval` của run đó quay về `comparing` để phân tích lại | P1-T3 |
| Giữ raw proposal ở chế độ debug | Bỏ hẳn khỏi UI; backend không trả proposal chưa verified | P1-T4 |
| Thiếu VAT/phí/lead time/warranty | Trả `needs_input` kèm field thiếu, không fallback | P2-T2 |
| Manager Reject | PR quay về `comparing`, run ghi lý do, buyer có thể phân tích lại | P2-T3 |
| Nối full graph vào UI | Không làm | P2-T5 |
| "Ngày chạy" trong `snapshot_revision` | Chỉ điều tra và báo cáo, chưa đổi hash | P3-T2 |
| Structured output của Groq | Chỉ bật nếu xác minh được model hỗ trợ, nếu không giữ JSON thường | P2-T1 |

## Điều kiện hoàn thành toàn bộ

- Test "raw LLM không tạo được PO" pass.
- Không còn `untrusted_proposal` hay `TEMPORARY_UNTRUSTED_APPROVAL_BYPASS` ngoài migration và test.
- Cập nhật tài liệu luồng hiện tại cho khớp với luồng mới (bạn tự làm hoặc giao agent sau cùng).
