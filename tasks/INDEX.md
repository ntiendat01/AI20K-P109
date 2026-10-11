# Task Index — Procurement Agent

| ID | Tiêu đề | Trạng thái | Phụ thuộc | Mô tả |
|----|---------|-----------|-----------|-------|
| T-01 | Skeleton graph chạy end-to-end với stub data | Todo | không | Dựng `state.py`, `graph.py`, `nodes.py` với stub ở mọi node; graph compile và chạy từ START → HITL-1 → HITL-2 → END bằng dữ liệu cứng |
| T-02 | Tạo PR & tải lên PDF | Todo | T-01 | API/model tạo case PR, nhận upload ≤10 PDF, validate số lượng/ngày/định dạng, chặn phân tích khi < 2 file (US-01.1, US-01.2, US-01.3) |
| T-03 | Trích xuất thông tin dòng hàng & chi phí | Todo | T-02 | Node `extract_documents` gọi PP-OCRv5 + Qwen3-8B; trả về structured fields (tên hàng, đơn giá, VAT, lead time, bảo hành) kèm `confidence_score` từng trường (US-02.1, US-02.2a, US-02.2b) |
| T-04 | Validation & confidence routing | Todo | T-03 | Node `validate_extraction` gán `needs_confirmation`; `confidence_router` gán `review_mode = mandatory/optional`; HITL-1 `interrupt()` chặn đúng điều kiện (US-02.4) |
| T-05 | UI đối soát HITL-1: side-by-side + sửa tay | Todo | T-04 | Màn hình hiển thị PDF gốc cạnh bảng trích xuất; highlight trường < 80%; cho phép sửa + lưu lịch sử; nút "Chốt dữ liệu" bị chặn khi còn trường chưa confirm (US-02.3a, US-02.3b, US-02.4) |
| T-06 | Chuẩn hóa UOM & tiền tệ | Todo | T-04 | Node `normalize` với bảng quy đổi đơn vị tính; gắn cờ "Cần quy đổi thủ công" khi đơn vị lạ; không tự đoán (US-03.1a) |
| T-07 | Tính TCO & ma trận so sánh | Todo | T-06 | Tool `calculate_tco` theo công thức cố định; tool `compare_suppliers` tạo ma trận N×5; highlight ô vượt ngưỡng 15% (US-03.2, US-03.3, US-04.1) |
| T-08 | Risk analysis: chi phí ẩn & lead time | Todo | T-07 | Tool `analyze_risks` phát hiện phí ngoài bảng giá chính; so sánh lead time với deadline PR; sinh `risk_flags` (US-04.2a, US-04.2b) |
| T-09 | LLM đề xuất NCC kèm evidence | Todo | T-07, T-08 | Node `decision_llm` → `generate_evidence`; đề xuất NCC với số liệu cụ thể; trích dẫn vị trí PDF; xử lý tie-break khi 2 NCC cách < 2% TCO (US-04.3a, US-04.3b) |
| T-10 | HITL-2: Buyer phê duyệt hoặc phản hồi | Todo | T-09 | `human_review_recommendation` interrupt(); `buyer_decision_router` → END hoặc `process_feedback` → quay lại `decision_llm` (US-04.3a) |
| T-13 | Bắt buộc HITL-1 cho mọi Extraction | Todo | T-04 | Xóa nhánh `"optional"` trong `confidence_router`; mọi extraction đều phải qua Buyer Review bất kể confidence score. Vi phạm contract hiện tại. |
| T-14 | Normalize đọc từ ConfirmedQuotation thay vì raw_extractions | Todo | T-13 | Thêm `confirmed_quotes` vào state; node `normalize` chuyển sang đọc dữ liệu đã Buyer chốt thay vì raw OCR output. |
| T-15 | Gắn AnalysisArtifact Envelope cho các node phân tích | Todo | T-14 | Wrap output TCO, risk, comparison, normalization vào `AnalysisArtifact` envelope; thêm `started/completed/failed` log event cho mỗi node. |
| T-16 | Xóa import schema legacy khỏi services | Todo | T-14 | Di chuyển `comparison.py` và `procurement/workflow.py` từ import bridge legacy (`schemas`, `evaluation`) sang canonical models (`analysis.comparison`, `approval`, `workflow`). |
| T-17 | Bổ sung Manager Approval và PO Service vào Graph | Todo | T-15, T-16 | Thêm node `manager_approval`, `buyer_action_router`, `manager_decision_router` vào graph; hoàn thiện luồng HITL-2 → Manager → PO issuance. |
