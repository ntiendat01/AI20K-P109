# Product Requirements Document (PRD): Module "monitor"

## 1. Giới thiệu (Introduction)

- **Tên dự án/Module:** Hệ thống Monitor & Observability (Dự án P-109)
- **Mục tiêu:** Cung cấp khả năng giám sát, gỡ lỗi và đo lường hiệu năng cho hệ thống AI Agent (LangGraph) xử lý Đề nghị mua sắm (PR) mà không can thiệp sâu vào codebase hiện tại của Backend.
- **Phạm vi (Scope):** Xây dựng module `monitor` độc lập, hỗ trợ theo dõi telemetry từ LLM/Agents và tài nguyên hệ thống (CPU/RAM).

## 2. Mục tiêu sản phẩm (Product Goals)

- **Zero-coupling Architecture:** Module `monitor` phải được thiết kế độc lập, sử dụng Facade/Adapter pattern để không gây phá vỡ kiến trúc Backend hiện tại.
- **Dual-tracking:** Tích hợp song song LangSmith và Langfuse để đánh giá và tận dụng điểm mạnh của cả hai nền tảng trong giai đoạn MVP.
- **Extensibility & Future-proofing:** Chuẩn bị sẵn các giao diện (interface chờ) để Core Agents có thể kết nối ngay khi hoàn thiện, đồng thời hỗ trợ mở rộng khả năng giám sát tài nguyên hệ thống (CPU/RAM).

## 3. Yêu cầu chức năng (Functional Requirements)

### 3.1. Theo dõi hoạt động của Agent (Agent Debugging & Tracing)

- Ghi nhận lại các thay đổi trạng thái (State Transitions) của LangGraph qua từng Node (OCR, Chuẩn hóa, So sánh).
- Lưu vết toàn bộ I/O thô: Prompt đầu vào, phản hồi của LLM, thông tin Tool Calling.
- Bắt và lưu trữ các Exception/Error xảy ra tại các Node.

### 3.2. Giám sát Hiệu năng & Chi phí LLM (Performance & Cost)

- Theo dõi mức độ sử dụng Token (Token Usage) ở cấp độ toàn bộ luồng và từng Node.
- Đo lường độ trễ (Latency) của từng lời gọi LLM và tổng thời gian hoàn thành của một PR.
- Ước tính chi phí quy đổi (Cost) theo từng model/API call.

### 3.3. Dual-Tracking (Langfuse & LangSmith)

- Hỗ trợ gửi telemetry đồng thời đến cả hai nền tảng thông qua bộ handler chung:
  - **LangSmith (Web Cloud):** Xem trên giao diện Web SaaS chính thức tại `https://smith.langchain.com`. Giúp debug trực quan và theo dõi luồng thực thi chi tiết của LangGraph.
  - **Langfuse (Localhost / Self-hosted):** Xem trên giao diện Localhost (mặc định tại `http://localhost:3000` thông qua Docker Compose). Giúp quản lý chi phí token, latency và feedback mà không đẩy dữ liệu ra bên ngoài.

### 3.4. Ghi nhận Đánh giá & Chất lượng (Quality & Feedback)

- Hỗ trợ lưu trữ điểm số Human-in-the-loop (HITL) khi người dùng duyệt hoặc từ chối kết quả do Agent đề xuất.
- Đánh giá chất lượng của tác vụ RAG (Retrieval-Augmented Generation) từ Vector DB.

### 3.5. Theo dõi Tài nguyên Hệ thống (System Resources Monitoring)

- Monitor các chỉ số phần cứng khi xử lý tác vụ nặng (ví dụ: OCR file PDF lớn).
- Cung cấp tính năng ghi log (System Logs) mức tiêu thụ CPU và RAM.
- Mở rộng để ghi nhận thời gian I/O (Database I/O, Network Latency) nếu cần thiết để phân biệt nút thắt cổ chai do Server hay API LLM.

## 4. Yêu cầu Phi chức năng & Kiến trúc (Non-Functional & Architectural Requirements)

### 4.1. Zero-coupling (Facade/Adapter Pattern)

- Thiết kế module dạng Wrapper/Facade bọc bên ngoài logic tracking cốt lõi.
- Codebase Backend chỉ cần import 1 dòng duy nhất để lấy `callbacks` (ví dụ: `get_tracing_callbacks()`) và truyền vào hàm `graph.invoke()`.
- Cấu hình (API Keys, Endpoints) phải được quản lý qua biến môi trường (.env), tách biệt hoàn toàn với logic mã nguồn.

### 4.2. Extensibility (Giao diện chờ - Mocking/Lazy Initialization)

- **Lazy Initialization:** Khởi tạo module monitor độc lập, không phụ thuộc vào trạng thái khởi tạo của đối tượng Agent.
- **Chế độ chờ:** Khi Core Agents chưa hoàn thiện, module có thể chạy ở chế độ giả lập (Mock) hoặc không hoạt động.
- **Dynamic Binding:** Các metrics mới sinh ra sau này phải được tiếp nhận dưới dạng Metadata linh hoạt (JSON/Dictionary) để module monitor không cần thay đổi source code khi Core Agents bổ sung feature.

## 5. Hướng dẫn Tích hợp dự kiến

```python
# Tại Backend codebase
from monitor import get_tracing_callbacks, log_system_resource

# Ghi log tài nguyên trước khi chạy tác vụ nặng
log_system_resource(action="start_pdf_processing")

# Gọi LangGraph với callback từ monitor (Hỗ trợ cả LangSmith và Langfuse)
graph.invoke(input_data, config={"callbacks": get_tracing_callbacks()})
```

## 6. Phân đoạn Triển khai (Phases)

- **Phase 1 (MVP & Dashboard Preview):**
  - Xây dựng module `monitor` khung sử dụng Facade pattern.
  - Viết bộ wrapper tích hợp dual-callback của LangSmith và Langfuse.
  - Viết script giả lập (Mock Simulator) để gửi chuỗi traces/spans thử nghiệm đến cả LangSmith UI và Langfuse UI.
  - **Kết quả thu được:** Đã có thể truy cập Dashboard của LangSmith và Langfuse để **xem trước (preview)** đồ thị trace, token usage, latency và biểu đồ thử nghiệm ngay cả khi Core Agents chưa hoàn thiện.
  - Viết helper function để log system resource (CPU/RAM).
- **Phase 2 (Integration):** Tích hợp trực tiếp module monitor vào Core Agents ngay khi nhóm Core Agents code xong interface đầu tiên.
- **Phase 3 (Optimization):** Phát triển hệ thống dashboard thu thập dữ liệu HITL Feedback nâng cao và cảnh báo chi phí token tự động.
