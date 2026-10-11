# Sơ đồ trạng thái phân tích mua sắm

`PurchaseRequest.status` là vòng đời nghiệp vụ của Phiếu đề nghị mua (PR).
Lần chạy phân tích bền vững và đề xuất đã đánh giá là các bản ghi riêng biệt;
chỉ một lần chạy `awaiting_review` có snapshot còn hiện hành mới được gửi duyệt.

| Sự kiện                                        | Trạng thái PR trước → sau          | Trạng thái lần chạy sau sự kiện                            | Hành động hợp lệ tiếp theo                                                                                      |
| ---------------------------------------------- | ---------------------------------- | ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Tải lên/xác nhận báo giá                       | `awaiting_quotation` → `comparing` | `not_started`                                              | Nhân viên mua sắm hoàn tất ít nhất 2 báo giá độc lập.                                                           |
| Bắt đầu phân tích                              | `comparing` → `comparing`          | `running`                                                  | API trả `202`; giao diện polling trạng thái. Bấm lại cùng snapshot dùng lại run đang chạy.                      |
| Worker bị dừng/quá ngưỡng                      | `comparing` → `comparing`          | `technical_failure`                                        | Khi đọc run quá thời gian cấu hình (mặc định 5 phút), hệ thống đánh dấu lỗi và cho phép thử lại.                |
| Phân tích khi thiếu trường bắt buộc            | `comparing` → `comparing`          | `needs_input`, có `missing_fields`                         | Mở báo giá và điền cách tính/thuế suất VAT, phí giao hàng, thời gian giao, bảo hành và các dòng hàng còn thiếu. |
| Proposal không hợp lệ nhưng có thể sửa         | `comparing` → `comparing`          | `repairable`                                               | Nhân viên mua sắm chạy phân tích lại.                                                                           |
| Provider quyết định hoặc kho bằng chứng bị lỗi | `comparing` → `comparing`          | `technical_failure`                                        | Thử chạy lại; JSON không hợp lệ không tạo evaluation hoặc quyền duyệt.                                          |
| Phân tích đã được kiểm chứng                   | `comparing` → `comparing`          | `awaiting_review`                                          | Gửi snapshot chưa thay đổi sang quản lý duyệt.                                                                  |
| Gửi duyệt                                      | `comparing` → `pending_approval`   | `awaiting_review`                                          | Quản lý phê duyệt, từ chối hoặc yêu cầu chỉnh sửa.                                                              |
| Quản lý phê duyệt                              | `pending_approval` → `approved`    | `approved`                                                 | PO chỉ được tạo từ snapshot đã kiểm chứng.                                                                      |
| Quản lý từ chối                                | `pending_approval` → `comparing`   | `rejected`, có `manager_note`                              | Nhân viên xem lý do, cập nhật nếu cần rồi phân tích lại.                                                        |
| Quản lý yêu cầu chỉnh sửa                      | `pending_approval` → `comparing`   | `awaiting_repair` hoặc `awaiting_input`, có `manager_note` | Nhân viên xử lý yêu cầu giải thích/dữ liệu/ưu tiên, sau đó phân tích lại.                                       |
| Nguồn hoặc báo giá thay đổi sau khi review     | `comparing`                        | Review cũ bị coi là stale; API trả `409`                   | Xác nhận lại báo giá hiện tại rồi phân tích lại.                                                                |

API trả `409` khi gọi sai thứ tự: chỉ được phân tích khi PR ở
`awaiting_quotation` hoặc `comparing`; gửi duyệt cần lần chạy đã kiểm chứng và
còn hiện hành; phản hồi của quản lý cần đề xuất đang ở `awaiting_review`.

## Kiểm tra thủ công giao diện

1. Xóa `lead_time_days` ở một báo giá đã xác nhận, mở màn hình so sánh và kiểm
   tra tên NCC, nút **Mở báo giá để bổ sung dữ liệu**, cùng điều hướng đến màn
   hình chỉnh sửa báo giá.
2. Cho provider test trả `DecisionProposal` đúng schema nhưng không nhất quán;
   kiểm tra trạng thái `repairable`, lý do hiển thị và nút **Chạy lại phân tích**.
3. Cho provider trả JSON hỏng ba lần; kiểm tra trạng thái **Phân tích chưa thành
   công**, thông báo retry an toàn và nút **Thử lại phân tích**, không có nút gửi
   duyệt.
4. Với vai trò quản lý, yêu cầu chỉnh sửa hoặc từ chối một đề xuất đã gửi duyệt;
   kiểm tra PR trở về `comparing`, nhân viên thấy ghi chú quản lý và có thể tạo
   một lần phân tích mới.

## Ranh giới graph

Luồng được gọi từ giao diện đi vào LangGraph tại `normalize` với
`confirmed_input=True`. Nhánh OCR/trích xuất đầy đủ
`extract_documents → validate_extraction → confidence_router → human_review_extraction`
cố ý **chưa được nối vào giao diện so sánh** theo quyết định mặc định của P2-T5.
