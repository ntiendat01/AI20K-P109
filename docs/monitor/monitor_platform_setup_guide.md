# Hướng dẫn thiết lập Dashboard cho Procurement AI Agent (Langfuse & LangSmith)

Dựa trên kiến trúc và mã nguồn tích hợp (tại `monitor/`), việc kết nối telemetry đã hoàn thiện 100%. Tuy nhiên, để tận dụng tối đa dữ liệu mà hệ thống gửi lên, cần thực hiện một số thiết lập trực tiếp trên giao diện Dashboard của **LangSmith** và **Langfuse**.

---

## 1. Nền tảng Langfuse (Dành cho Product / Business)

Langfuse tập trung mạnh vào việc phân tích luồng người dùng (sessions) và đánh giá chất lượng trải nghiệm (evaluations).

### Xem theo Tab "Sessions" thay vì "Traces"
Vì hệ thống có cơ chế Human-In-The-Loop (HITL), một quy trình Mua sắm có thể bị ngắt quãng vài tiếng hoặc vài ngày (chờ con người duyệt/chỉnh sửa). Nhờ cấu hình biến môi trường `LANGFUSE_SESSION_ID_PREFIX` trong adapter, bạn chỉ cần vào tab **Sessions**. Langfuse sẽ tự động gom nối tất cả các trace rời rạc của cùng một `thread_id` lại thành một luồng hoàn chỉnh duy nhất (từ lúc extract báo giá đến khi buyer duyệt cuối cùng).

### Thiết lập Dashboard theo Tags
Trong `langfuse_adapter.py`, hệ thống tự động đẩy lên các `tags` (như `procurement`, `phase: extraction`, `phase: decision`...). Bạn nên truy cập Dashboard của Langfuse và tạo các biểu đồ (chart) filter theo các tags này. Việc này sẽ giúp theo dõi trực quan:
- Phase nào đang tiêu tốn nhiều token LLM nhất.
- Phase nào thường xuyên bị delay lâu nhất do HITL.

### Tạo Custom Scores (Khuyên dùng)
Hãy vào mục **Scores** và tạo một score name mới (ví dụ: `buyer_revision`) tương ứng với lúc biến `revise_count` tăng lên trong hệ thống. Việc này cho phép Langfuse tự động vẽ biểu đồ tỷ lệ LLM làm hài lòng Buyer ngay từ lần đầu tiên (First-time Acceptance Rate) mà không cần lập trình thêm.

---

## 2. Nền tảng LangSmith (Dành cho Developer / Debugging)

LangSmith cực kì hiệu quả trong việc mổ xẻ execution tree và quản lý dataset để optimize LLM prompts.

### Lưu filter theo "Metadata"
Hệ thống (`SystemAdapter`) đang truyền toàn bộ `metadata` như `node_name`, `reason` lên LangSmith.
- Hãy vào giao diện Traces của LangSmith và nhập câu query: `has_metadata: {"reason": "confidence_low"}`.
- Lưu (Save) filter này lại. Nó sẽ giúp team Dev lập tức tìm ra các trường hợp LLM bóc tách OCR thất bại để debug.

### Sử dụng Annotation Queues cho HITL
LangSmith có tính năng *Annotation Queues*. Với những trace bị rơi vào nhánh `human_review_extraction` (do chất lượng dữ liệu quá kém, cần con người sửa đổi), bạn có thể cấu hình đẩy thẳng các trace đó vào Queue trên LangSmith. Tại đây, đội QA có thể đánh giá (annotate), chấm điểm prompt, hoặc bổ sung dữ liệu vào Dataset để fine-tune model.

### Tạo Dataset từ các cảnh báo Revision (Alerts)
Những trace sinh ra cảnh báo khi `revise_count >= 3` chứng tỏ LLM đang suy luận sai logic nghiệp vụ liên tục.
- Hãy filter các trace này trên LangSmith.
- Click **"Add to Dataset"** để lưu giữ chúng làm test cases.
- Sử dụng dataset này để chạy evaluation tự động (Regression Testing) mỗi khi cập nhật cấu trúc Prompt trong các phiên bản sau.
