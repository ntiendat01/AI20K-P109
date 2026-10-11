# 📋 Lập kế hoạch: Cài đặt và Thiết lập Monitor System v2

**Mục tiêu:** Tích hợp và cấu hình hệ thống Monitor v2 cho Procurement AI Agent, tương thích hoàn toàn với kiến trúc 5 tầng Evaluation và Evidence Grounding.

---

## 1. Tóm tắt (Summary)
Task này thiết lập module Monitor sử dụng Facade pattern để kết nối đồ thị LangGraph với LangSmith, Langfuse, DeepEval và hệ thống ghi log cục bộ. Trọng tâm là theo dõi chính xác các checkpoint HITL, các lỗi hallucination trong quá trình retrieve evidence, và phân tích cấu trúc feedback của người dùng.

## 2. Phạm vi File (File Scope)

| File | Hành động | Ghi chú |
| --- | --- | --- |
| `monitor/v2/core/facade.py` | Tạo mới | Chứa `MonitorFacade` điều phối các adapters. |
| `monitor/v2/adapters/langsmith_adapter.py` | Tạo mới | Adapter cấu hình tracing và tagging cho LangSmith. |
| `monitor/v2/adapters/langfuse_adapter.py` | Tạo mới | Adapter gom Session và xử lý Typed Feedback cho Langfuse. |
| `monitor/v2/adapters/deepeval_adapter.py` | Tạo mới | Adapter đẩy metric chấm điểm LLM lên DeepEval. |
| `monitor/v2/adapters/system_adapter.py` | Tạo mới | Ghi log CPU/RAM và application metadata. |
| `monitor/v2/__init__.py` | Tạo mới | Export public functions (e.g. `get_tracing_callbacks`, `log_feedback`). |
| `.env` | Chỉnh sửa | Bổ sung các cấu hình API Key và cờ kích hoạt cho hệ thống monitor. |

**Không được đụng:**
- Các file core logic của agents (`agents/`, `graph/`) ngoại trừ việc import 1 dòng facade để tiêm (inject) callbacks.

## 3. Các bước (Steps)

**Bước 1: Cấu hình biến môi trường**
- **Mục tiêu:** Cung cấp thông tin kết nối và tùy chọn kích hoạt cho các adapters.
- **File sửa:** `.env`
- **Chi tiết:** Thêm `LANGSMITH_ENABLED`, `LANGFUSE_ENABLED`, `DEEPEVAL_TELEMETRY_API_KEY`, `LANGFUSE_SESSION_ID_PREFIX=procurement-`.
- **Commit:** `chore(monitor): add monitor v2 env configs`

**Bước 2: Xây dựng các Adapters**
- **Mục tiêu:** Tạo các class xử lý logic kết nối riêng biệt cho từng nền tảng.
- **File sửa:** `monitor/v2/adapters/*.py`
- **Chi tiết:** 
  - `langsmith_adapter`: cấu hình Project Name và gắn tags.
  - `langfuse_adapter`: khởi tạo client, cấu hình session prefix.
  - `deepeval_adapter`: cấu hình gửi `Completeness`, `Justification`, `Risk` metrics.
  - `system_adapter`: logic lấy metric OS.
- **Commit:** `feat(monitor): implement v2 telemetry adapters`

**Bước 3: Xây dựng Facade và Public Interface**
- **Mục tiêu:** Đóng gói toàn bộ adapter qua một class `MonitorFacade` duy nhất.
- **File sửa:** `monitor/v2/core/facade.py`, `monitor/v2/__init__.py`
- **Chi tiết:** Cung cấp các method `get_tracing_callbacks()`, `log_hitl_interrupt()`, `log_feedback()`, `log_evaluation_metrics()`. Singleton instantiation trong `__init__.py`.
- **Commit:** `feat(monitor): setup v2 facade pattern`

**Bước 4: Setup LangSmith & Langfuse Dashboards (Manual/Admin)**
- **Mục tiêu:** Khởi tạo các filter và dashboard trên nền tảng cloud.
- **Chi tiết:** 
  - Trên LangSmith: Save filter `has_tag: "evidence_retrieval" AND has_metadata: {"support_status": "not_found"}` thành "Hallucination Watch".
  - Trên Langfuse: Add custom score `first_time_acceptance` để đo lường KPI feedback.

## 4. Thay đổi contract/schema (CẦN DUYỆT)
*Không thay đổi contract của Core AI, chỉ bổ sung metadata model phục vụ ghi log.*

**Monitor Feedback Schema (Internal):**
```json
{
  "generation_id": "string",
  "idempotency_key": "string",
  "revision_type": "string",
  "note": "string"
}
```

## 5. Rủi ro và giả định
- **Rủi ro:** Gọi API telemetry đồng bộ có thể làm chậm luồng agent. 
- **Giả định:** Các nền tảng SDK (Langfuse/LangSmith) mặc định sử dụng cơ chế bắn log bất đồng bộ (background thread) để không gây block Main Thread.

## 6. Câu hỏi cần quyết
- Có cần thiết lập môi trường self-hosted cho Langfuse bằng docker-compose ở v2 không, hay chuyển thẳng lên Langfuse Cloud?
