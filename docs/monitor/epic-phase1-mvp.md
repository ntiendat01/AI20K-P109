# Epic 1: Phase 1 - MVP & Dashboard Preview (Dual-Tracking Monitor)

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
