# Tickets: Monitor Module (All Phases)

Dựa vào `prd-monitor.md`, dưới đây là việc bóc tách toàn bộ các Epic và Ticket cho toàn bộ các Phase của module Monitor.

## 🎫 Epic 1: Phase 1 - MVP & Dashboard Preview (Dual-Tracking Monitor)

*(Giai đoạn này tập trung xây dựng nền tảng và có thể giả lập ngay lập tức mà chưa cần Core Agents)*

### 🎟️ Ticket 1.1: Thiết lập môi trường Langfuse Local (Docker Setup)
**Mô tả:** Cấu hình và dựng môi trường Langfuse UI cùng với database PostgreSQL trên localhost.
**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Tạo `docker-compose.yml` với dịch vụ `langfuse-server` và `db`.
- [ ] Môi trường khởi chạy thành công, truy cập được Dashboard tại `http://localhost:3000`.
- [ ] Database PostgreSQL lưu trữ dữ liệu an toàn qua volume `langfuse_data`.

### 🎟️ Ticket 1.2: Xây dựng bộ khung Module và Facade Pattern
**Mô tả:** Khởi tạo cấu trúc thư mục và class `MonitorFacade` để đáp ứng tiêu chí Zero-coupling.
**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Tạo đủ thư mục: `core/`, `adapters/`, `config/`, `scripts/`.
- [ ] Xây dựng class `MonitorFacade` (dạng Singleton).
- [ ] Cung cấp public API tại `monitor/__init__.py`: `get_tracing_callbacks()` và `log_system_resource()`.

### 🎟️ Ticket 1.3: Tích hợp LangSmith & Langfuse Adapters
**Mô tả:** Triển khai các Adapter giao tiếp với API của LangSmith và Langfuse.
**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Viết `langsmith_adapter.py` để sinh callback LangSmith.
- [ ] Viết `langfuse_adapter.py` để sinh callback Langfuse.
- [ ] Kết hợp 2 adapter vào facade để trả về danh sách gộp nếu được kích hoạt qua `.env`.

### 🎟️ Ticket 1.4: Xây dựng System Resource Adapter
**Mô tả:** Viết adapter giám sát CPU/RAM hệ thống cho các tác vụ nặng.
**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Tạo `system_adapter.py` ghi nhận mức tải (CPU, RAM).
- [ ] Định nghĩa chuẩn dữ liệu metadata để xuất ra log file/console.

### 🎟️ Ticket 1.5: Phát triển Mock Simulator & Kiểm chứng
**Mô tả:** Chạy kịch bản giả lập (Simulator) để kiểm tra luồng telemetry.
**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Viết script `mock_simulator.py` mô phỏng luồng LangChain (OCR -> Chuẩn hóa -> So sánh).
- [ ] Giả lập độ trễ (latency), tải tài nguyên (CPU spike) và văng lỗi (Exception).
- [ ] Verify dữ liệu có xuất hiện đồng thời trên LangSmith Cloud và Langfuse Local.

---

## 🎫 Epic 2: Phase 2 - Core Agents Integration

*(Giai đoạn này được thực hiện khi đội Core Agents bắt đầu hoàn thiện các Interface cơ bản)*

### 🎟️ Ticket 2.1: Tích hợp Monitor vào Node OCR
**Mô tả:** Gắn monitor module vào tác vụ đọc, xử lý file hóa đơn, chứng từ (OCR) để đo hiệu suất xử lý file nặng.
**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Import `get_tracing_callbacks` và truyền vào luồng gọi LLM ở Node OCR.
- [ ] Đảm bảo `log_system_resource` được gọi trước và sau khi phân tích PDF/Ảnh để giám sát I/O và CPU/RAM peak.
- [ ] Dữ liệu token usage của Node OCR hiển thị rành mạch.

### 🎟️ Ticket 2.2: Tích hợp Monitor vào Node Chuẩn hóa & So sánh
**Mô tả:** Tích hợp tracing vào các logic quyết định (Decision Making) và trích xuất dữ liệu của LLM.
**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Import và chèn callback vào luồng invoke LangGraph của phần Chuẩn hóa và So sánh Đề nghị mua sắm (PR).
- [ ] Kiểm chứng các Input Prompts và Output Responses được bắt đầy đủ mà không lộ thông tin nhạy cảm.
- [ ] Các exception khi parse JSON của LLM được log dưới dạng Error/Warning trên Langfuse.

---

## 🎫 Epic 3: Phase 3 - Optimization & Advanced Features

*(Giai đoạn hoàn thiện, bổ sung đo lường chất lượng qua HITL và quản lý chi phí)*

### 🎟️ Ticket 3.1: Cơ chế Thu thập Đánh giá HITL (Human-in-the-loop)
**Mô tả:** Hỗ trợ lưu trữ điểm số phản hồi từ user (khi user chốt duyệt PR hoặc sửa đổi đề xuất của LLM).
**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Bổ sung public method vào `MonitorFacade`: `log_user_feedback(trace_id, score, comment)`.
- [ ] Triển khai logic gửi feedback (scores = 0 hoặc 1) thông qua API của Langfuse hoặc LangSmith.
- [ ] Liên kết được điểm số với đúng `trace_id` của phiên xử lý (Run ID).

### 🎟️ Ticket 3.2: Đo lường chất lượng RAG (Vector DB)
**Mô tả:** Ghi nhận và theo dõi chất lượng các luồng truy vấn tới cơ sở dữ liệu Vector.
**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Tạo Custom Spans để bọc riêng khối mã thực thi lệnh `Retriever`.
- [ ] Đo đạc độ trễ của riêng việc gọi Vector DB thay vì gọi LLM.
- [ ] Lưu lại các documents được trả về vào metadata để phục vụ audit.

### 🎟️ Ticket 3.3: Quản lý ngân sách (Token Cost Alerting)
**Mô tả:** Cảnh báo phòng ngừa tình trạng vượt mức chi tiêu token (Cost spike) đối với các model đắt tiền (GPT-4 / Opus).
**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Lập cấu hình giới hạn (budget) trên Langfuse UI hoặc viết cronjob gọi API.
- [ ] Bắn tín hiệu cảnh báo (qua console log ưu tiên cao hoặc kết nối webhook) khi một phiên chạy tiêu tốn chi phí bất thường (> $X/run).
