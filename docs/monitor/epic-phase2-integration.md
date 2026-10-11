# Epic 2: Phase 2 - Core Agents Integration

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
