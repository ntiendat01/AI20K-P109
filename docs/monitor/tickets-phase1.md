# Tickets: Phase 1 - MVP & Dashboard Preview (Dual-Tracking Monitor)

Dựa vào `prd-monitor.md` và `architecture-monitor.md`, dưới đây là việc bóc tách chi tiết Phase 1 thành các ticket phục vụ cho quá trình phát triển (tuân thủ chuẩn BMad Ticketing).

## Epic: Phase 1 - MVP & Dashboard Preview

---

### 🎟️ Ticket 1: Thiết lập môi trường Langfuse Local (Docker Setup)
**Mô tả:** Cấu hình và dựng môi trường Langfuse UI cùng với database PostgreSQL trên localhost để phục vụ việc debug và monitor mà không cần đẩy dữ liệu ra bên ngoài.

**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Tạo file `docker-compose.yml` tại thư mục gốc của module `monitor` với đầy đủ cấu hình cho `langfuse-server` và `db` (như trong bản kiến trúc).
- [ ] Môi trường khởi chạy thành công qua lệnh `docker-compose up -d`.
- [ ] Truy cập được Langfuse Dashboard tại `http://localhost:3000`.
- [ ] Cơ sở dữ liệu PostgreSQL hoạt động ổn định và có gán volume `langfuse_data`.

---

### 🎟️ Ticket 2: Xây dựng bộ khung Module và Facade Pattern
**Mô tả:** Khởi tạo cấu trúc thư mục tiêu chuẩn cho module và viết bộ khung Facade pattern (`MonitorFacade`) để thực hiện Zero-coupling cho hệ thống.

**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Tạo đầy đủ cấu trúc thư mục: `monitor/core`, `monitor/adapters`, `monitor/config`, và `monitor/scripts`.
- [ ] Viết cấu hình load biến môi trường tại `config/settings.py`.
- [ ] Viết class `MonitorFacade` tại `core/facade.py` theo mẫu Singleton (khai báo các Adapter trống để chờ tích hợp).
- [ ] Định nghĩa Public Interface tại `monitor/__init__.py` gồm các hàm: `get_tracing_callbacks()` và `log_system_resource(action, metadata)`.

---

### 🎟️ Ticket 3: Tích hợp LangSmith & Langfuse Adapters
**Mô tả:** Triển khai các Adapter kết nối với API của LangSmith và Langfuse để lấy về các tracing callbacks cho LangGraph. 

**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Hoàn thiện `adapters/langsmith_adapter.py` để lấy callback của LangSmith (tự động link tới `https://smith.langchain.com`).
- [ ] Hoàn thiện `adapters/langfuse_adapter.py` để sinh ra callback tương ứng của Langfuse (gắn endpoint vào localhost:3000).
- [ ] Tích hợp 2 Adapter này vào `MonitorFacade.get_tracing_callbacks()`.
- [ ] Trả về danh sách gộp (List) các callback từ cả 2 nền tảng nếu cả 2 được enable trong `.env`.

---

### 🎟️ Ticket 4: Xây dựng System Resource Adapter
**Mô tả:** Cung cấp tính năng giám sát tài nguyên phần cứng (CPU/RAM) bên lề các tác vụ nặng (như OCR) mà không phụ thuộc vào LangChain.

**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Tạo file `adapters/system_adapter.py` với class `SystemAdapter`.
- [ ] Viết hàm `log_usage(action, metadata)` ghi nhận mức tiêu thụ CPU, RAM hiện tại của tiến trình.
- [ ] Kết nối hàm này vào `MonitorFacade.log_system_resource(...)`.
- [ ] (Option) Lưu log vào một file local hoặc in ra terminal với format JSON dễ đọc.

---

### 🎟️ Ticket 5: Phát triển Mock Simulator & Kiểm chứng
**Mô tả:** Do Core Agents chưa hoàn thiện, cần xây dựng một kịch bản giả lập (Simulator) để kiểm tra luồng Dual-tracking và giao diện dashboard.

**Tiêu chí nghiệm thu (Acceptance Criteria):**
- [ ] Viết script giả lập tại `scripts/mock_simulator.py`.
- [ ] Khởi tạo một dummy workflow (VD: OCR -> Chuẩn hóa -> So sánh) sử dụng Dummy LLM hoặc `RunnableLambda`.
- [ ] Chèn `config={"callbacks": get_tracing_callbacks()}` vào lệnh gọi giả lập.
- [ ] Bổ sung các kịch bản: Random delay (`time.sleep`) để tạo Latency và cố tình văng lỗi (`raise Exception`) để test log lỗi.
- [ ] Gọi hàm `log_system_resource("start_ocr_mock")` để kiểm tra log CPU/RAM.
- [ ] **Nghiệm thu cuối:** Dữ liệu traces, span, error, token usage hiện lên song song tại Dashboard LangSmith (Cloud) và Langfuse (Localhost).
