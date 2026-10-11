# Epic 3: Phase 3 - Optimization & Advanced Features

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
