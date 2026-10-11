# Research & Strategy: Hệ thống Monitor Kép (Langfuse & LangSmith)

**Dự án:** P-109 (AI20K Build Phase)
**Hạng mục:** Hệ thống Monitor & Observability
**Trạng thái:** Bản nháp phân tích (Giai đoạn 1 - BMAD)

---

## 1. Bối cảnh & Yêu cầu
- **Kiến trúc lõi:** Hệ thống sử dụng LangGraph để điều phối các Agent xử lý Đề nghị mua sắm (PR).
- **Phân tách trách nhiệm:** Backend/Frontend và DB do team khác phát triển. Module `monitor` phải độc lập, hạn chế tối đa việc can thiệp sâu vào codebase chung (Zero-coupling).
- **Thách thức:** Các Core Agents hiện đang phát triển và chưa hoàn thiện, vì vậy hệ thống Monitor phải có thiết kế linh hoạt, sẵn sàng mở rộng và dễ dàng cập nhật/kết nối sau khi Core Agents định hình.
- **Mục tiêu:** Cung cấp cả tính năng gỡ lỗi chuyên sâu (Debug) và quan sát tổng thể (Metrics/Resources) qua việc đánh giá song song Langfuse và LangSmith.

## 2. Các nhóm Yếu tố cần Monitor (Traces & Metrics)

Hệ thống được thiết kế để bao phủ 4 khía cạnh chính:

### 2.1. Nhóm Debug Agent (Truy vết chi tiết)
- **State Transitions:** Biến đổi trạng thái của LangGraph qua từng Node (OCR, Chuẩn hóa, So sánh).
- **I/O Thô (Raw):** Prompt đầu vào và phản hồi thô của LLM trước khi parse.
- **Tool Calling:** Tham số truyền vào và kết quả trả về của các công cụ (như truy vấn Vector DB, API OCR).
- **Exceptions:** Bắt và lưu vết các lỗi cục bộ tại từng Node.

### 2.2. Nhóm Hiệu năng & Chi phí LLM (LLM Performance & Cost)
- **Token Usage:** Theo dõi số lượng Token đầu vào/ra theo toàn bộ luồng hoặc từng Node.
- **Latency (LLM):** Độ trễ của mỗi luồng gọi API LLM và tổng thời gian hoàn thành 1 PR.
- **Cost:** Ước tính chi phí quy đổi ra USD dựa trên biểu giá model.

### 2.3. Nhóm Hiệu năng Tài nguyên Hệ thống (System Resources)
*Nhóm này được bổ sung để giám sát sức khỏe của máy chủ chạy Agent/Backend, giúp phân biệt lỗi do LLM chậm hay do server quá tải.*
- **CPU & RAM Usage:** Mức tiêu thụ CPU/RAM trong quá trình Agent thực thi tác vụ nặng (như parse file PDF lớn).
- **I/O Bottlenecks:** Thời gian đọc/ghi DB và thời gian chờ mạng (Network I/O).
*(Ghi chú: Đối với tài nguyên hệ thống, ngoài telemetry của Langfuse/LangSmith, có thể cần xuất log định dạng chuẩn để dễ tích hợp với các công cụ như Prometheus/Grafana hoặc Datadog nếu team DevOps yêu cầu).*

### 2.4. Nhóm Đánh giá Chất lượng (Quality & Feedback)
- **Human-in-the-loop (HITL) Score:** Ghi nhận quyết định của người duyệt (Duyệt/Từ chối) thành điểm số đánh giá độ chính xác của Agent.
- **RAG Retrieval Quality:** Đánh giá số lượng và độ liên quan của policy mua sắm được truy xuất từ VectorDB.

## 3. Chiến lược đối phó với sự thay đổi (Core Agents chưa hoàn thiện)

Vì các Core Agents vẫn đang trong quá trình phát triển, chiến lược thiết kế cho `monitor` sẽ tuân theo nguyên tắc **Giao diện chờ (Facade/Adapter Pattern)**:

1. **Định nghĩa Giao diện (Interface) trước:** Thư mục `monitor` sẽ cung cấp sẵn các hàm chuẩn (ví dụ: `get_monitor_callbacks()`, `log_system_resource()`).
2. **Khởi tạo độc lập (Lazy Initialization):** Module monitor không phụ thuộc vào object của Agent. Khi Core Agent chưa xong, monitor có thể chạy giả lập (Mocking) hoặc ở trạng thái "ngủ".
3. **Cập nhật động (Dynamic Binding):** Các metrics mới được Agent sinh ra sau này có thể truyền vào monitor dưới dạng `metadata` linh hoạt (JSON/Dict) thay vì hard-code cấu trúc cố định. Điều này đảm bảo khi Agent thêm tính năng mới, monitor không cần viết lại mã nguồn.

## 4. Đánh giá: Langfuse vs LangSmith

| Tiêu chí | LangSmith | Langfuse |
| :--- | :--- | :--- |
| **Debug Agent (LangGraph)** | **Xuất sắc**. Trace trực quan từng node, edge, state. Rất tốt để phát triển. | Tốt, nhưng cần setup callback kỹ hơn để hiện đẹp đồ thị. |
| **Quản lý Chi phí & Tổng quan**| Khá. Trả phí cao khi scale. | **Xuất sắc**. Quản lý chi phí token rất tốt, dễ self-host. |
| **Gắn Feedback (Chất lượng)** | Có hỗ trợ qua API. | Cực kỳ trực quan, tách biệt rõ ràng luồng Score. |
| **Giám sát System Resources** | Không chuyên biệt (tập trung LLM). | Không chuyên biệt (tập trung LLM). |

**Kết luận:** Chạy song song cả hai là phương án tối ưu trong giai đoạn MVP để so sánh. Tài nguyên Server (CPU/RAM) nên được log qua thư viện logging chuẩn của Python để tương thích với các công cụ APM khác.

## 5. Đề xuất Kiến trúc Tích hợp (Zero-coupling)

Tạo thư mục `monitor/` chứa các thành phần bọc (wrapper). Tại BE, chỉ cần import một dòng duy nhất để lấy `callbacks` và đưa vào hàm `invoke` của LangGraph.
```python
# Ví dụ sự thay đổi mong đợi ở BE (rất nhỏ)
from monitor import get_tracing_callbacks

# Truyền callbacks vào lúc gọi LLM hoặc LangGraph
graph.invoke(input_data, config={"callbacks": get_tracing_callbacks()})
```
