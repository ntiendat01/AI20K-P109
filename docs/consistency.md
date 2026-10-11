# Nhất quán giữa evaluation và procurement workflow

`evaluation.sqlite` là nguồn sự thật cho proposal đã được kiểm chứng;
`procurement-workflow.sqlite` lưu snapshot chạy và finalization command. PR và
PO hiện ở repository JSON riêng. Không có transaction phân tán, nên mỗi bước
ghi phải có thứ tự và idempotency rõ ràng.

| Điểm ghi | Thứ tự bền vững | Lý do và retry |
| --- | --- | --- |
| Bắt đầu analysis | Lưu run `running` trong procurement trước, sau đó worker chạy graph | HTTP 202 có ID để polling; process chết được phát hiện timeout khi đọc. |
| Kết thúc analysis | Evaluation workflow ghi/đánh giá proposal trước; sau đó cập nhật run với `evaluation`, review và trạng thái cuối | Không có run `awaiting_review` hợp lệ nếu evaluation không được lưu. |
| Submit approval | PR chuyển `comparing` → `pending_approval` sau khi `ensure_current()` kiểm snapshot/review | Không có DB evaluation thay đổi ở bước này. |
| Feedback approve | `evaluation.feedback()` ghi receipt và trạng thái `approved` trước; sau đó ghi `finalization` command bằng `INSERT OR IGNORE` | Receipt và command lặp được an toàn với cùng `idempotency_key`. |
| Tạo PO/finalize | Tạo PO bằng UUID xác định từ `(recommendation_id, version)`; sau đó update PR approved; cuối cùng update run approved | Nếu lỗi sau PO nhưng trước PR/run, retry/reconcile dùng cùng PO ID nên không tạo PO trùng và hoàn tất phần còn thiếu. |
| Reject/revise | Evaluation receipt trước, sau đó PR và run phản chiếu trạng thái/yêu cầu | Không thể biến proposal chưa kiểm chứng thành PO. |

## Phát hiện lệch

Chạy lệnh chỉ đọc sau deploy hoặc khi có sự cố:

```sh
.venv/bin/python3 scripts/check_procurement_consistency.py
```

Lệnh in JSON `findings`, thoát mã `1` nếu có lệch và không replay/sửa dữ liệu.
Nó phát hiện tối thiểu: run `awaiting_review` không có recommendation,
run/PR `approved` khi evaluation chưa approved, PR approved không có PO và PO
không có analysis run hoặc thuộc PR khác. Khôi phục có chủ đích dùng
`ProcurementWorkflow.reconcile()` sau khi đã xem finding; không dùng audit để
tự sửa.

## Giới hạn hiện tại

Đây vẫn là consistency kiểu saga trong một process, không phải atomic
transaction xuyên SQLite/JSON hay hàng đợi bền vững. Nhiều worker/process cùng
ghi cần một task riêng (ví dụ DB chung hoặc job queue) trước khi mở rộng tải.
