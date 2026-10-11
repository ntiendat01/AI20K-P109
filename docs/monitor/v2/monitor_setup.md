# Hướng dẫn Thiết lập Theo dõi (Monitor Setup)

Dựa trên cập nhật code mới nhất từ nhánh `refactor/fe_be` vào hệ thống, bao gồm các cấu trúc của LangGraph (`src/agents/graph.py`) và State (`src/agents/state.py`), dưới đây là hướng dẫn thiết lập hệ thống monitor (theo dõi) cho Procurement Agent.

## 1. Mục tiêu Theo dõi (Monitor Objectives)
- **Luồng trạng thái (Workflow Status)**: Theo dõi tiến trình của Agent thông qua các node, đặc biệt là trạng thái của workflow như `technical_failure`, `awaiting_review` hoặc khi cần xác nhận (`unconfirmed`).
- **Lưu trữ trạng thái (State Persistence)**: Theo dõi trạng thái đồ thị qua `MemorySaver()` (hoặc Checkpointer database trong production) để cho phép Human-in-the-loop (HITL) xác nhận và resume quá trình.
- **Hiệu suất LLM**: Theo dõi kết quả đầu ra của `decision_llm` và kết quả đánh giá (`evaluation_result`).

## 2. Các Chỉ số & Fields Cần Theo dõi (Key Metrics to Monitor)
Theo `ProcurementAgentState` (`src/agents/state.py`), các trường dữ liệu sau cần được monitor sát sao trên Log/Tracing system (ví dụ: LangSmith, Datadog):
- `workflow_status`: Cho biết tiến trình đang ở đâu (ví dụ: `technical_failure`, `awaiting_review`). 
- `evaluation_result`: Dữ liệu đánh giá (chứa `code` hoặc kết quả model dump).
- `decision_proposal` & `decision_context`: Dữ liệu đầu vào và đề xuất từ `decision_llm`.
- Trạng thái báo giá (`normalized_quotes`): Đặc biệt lưu ý cờ `needs_confirmation` và `confirmed_by_human`. 

## 3. Theo dõi Luồng Xử lý (Graph Execution Flow)
Graph (`src/agents/graph.py`) có 2 graph chính: `build_graph` và `build_decision_pipeline_graph`.

### Các điểm Routing quan trọng (Routing Points):
1. **validate_extraction -> confidence_router**:
   - Theo dõi tỷ lệ rẽ nhánh vào `human_review_extraction` (mandatory review) so với đi thẳng vào `normalize` (optional).
   - *Mục tiêu*: Đánh giá mức độ tự tin (confidence) của model trích xuất. Tỷ lệ vào `human_review_extraction` cao nghĩa là chất lượng trích xuất đang thấp, cần điều chỉnh prompt.

2. **normalize -> check_data_ready**:
   - Đếm số lượng transaction rẽ vào nhánh `unconfirmed` (kết thúc tại `END` để đợi người dùng) so với `ready` (tiếp tục vào `decision_llm`).
   - *Mục tiêu*: Xác định điểm nghẽn do chờ phản hồi xác nhận từ người mua.

### Lưu ý về node Evaluate:
Hiện tại trong `build_graph`, các edges tới node `evaluate` đang bị comment out:
```python
# graph.add_edge("decision_llm", "evaluate")
# graph.add_edge("evaluate", END)
graph.add_edge("decision_llm", END)
```
*Hành động monitor*: Cần theo dõi sự thay đổi của đoạn code này. Khi bật lại node `evaluate`, cần thêm alerting (cảnh báo) cho logic context evaluation qua `evaluation_workflow.submit()`. Đặc biệt chú ý alert nếu trả về lỗi: `{"workflow_status": "technical_failure", "evaluation_result": {"code": "EVALUATION_CONTEXT_NOT_CONFIGURED"}}`.

## 4. Công cụ Khuyến nghị (Recommended Tools)

### A. LangSmith (Dành cho LLM & LangGraph Tracing)
- Bật biến môi trường `LANGCHAIN_TRACING_V2=true` để tự động track toàn bộ execution của các node (`extract_documents`, `decision_llm`,...).
- Tạo các filter/dashboard trên LangSmith để đếm số lượng state kết thúc bằng `workflow_status = technical_failure`.

### B. Custom Application Logging (Datadog / ELK)
Log lại (emit logs) mỗi khi có thay đổi trạng thái (state transition) đối với:
- `recommendation_id` và `recommendation_version` mới được sinh ra.
- Event: "Chờ Human Feedback" (dựa trên field `require_explicit_confirmation`).
- Theo dõi các event khi graph bị treo do thiếu dependency (như mô tả trong docstring của `build_graph`).

## 5. Triển khai Checkpointer Monitor
Mặc định graph đang dùng `MemorySaver()` để lưu memory:
```python
graph.compile(checkpointer=MemorySaver())
```
Khi đưa lên production, nếu thay thế bằng database saver (như Postgres Saver) để phục vụ HITL bền vững (durable), cần set up monitor cho:
- Kích thước lưu trữ của các checkpoint row.
- Tốc độ read/write khi khôi phục state từ thread ID mỗi khi Resume.
