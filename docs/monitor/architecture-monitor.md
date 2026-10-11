# Technical Architecture: Monitor Module

## 1. Tổng quan (Overview)
Module `monitor` được thiết kế nhằm cung cấp khả năng quan sát (observability) cho hệ thống AI Agent (LangGraph) với kiến trúc **Zero-coupling**. Bằng cách sử dụng **Facade Pattern** và **Adapter Pattern**, module tách biệt hoàn toàn Core Agents khỏi các công cụ giám sát thực tế (LangSmith, Langfuse, System Monitor). Điều này cho phép Core Agents tích hợp khả năng theo dõi chỉ bằng 1 dòng code duy nhất.

## 2. Cấu trúc thư mục (Directory Structure)
```text
monitor/
├── __init__.py                # Public API (Facade methods: get_tracing_callbacks, log_system_resource)
├── core/                      # Chứa logic điều phối và Facade cốt lõi
│   ├── __init__.py
│   └── facade.py              # Class MonitorFacade (Singleton)
├── adapters/                  # Chứa các Adapter giao tiếp với nền tảng cụ thể
│   ├── __init__.py
│   ├── langsmith_adapter.py   # Tích hợp LangSmith
│   ├── langfuse_adapter.py    # Tích hợp Langfuse
│   └── system_adapter.py      # Tích hợp giám sát CPU/RAM hệ thống
├── config/                    # Quản lý cấu hình
│   ├── __init__.py
│   └── settings.py            # Load cấu hình từ biến môi trường (.env)
├── scripts/                   # Các script tiện ích và giả lập
│   └── mock_simulator.py      # Script giả lập cho Phase 1
└── docker-compose.yml         # Cấu hình dựng Langfuse ở localhost
```

## 3. Cấu trúc Class và Hàm (Facade Pattern)

### 3.1. Facade Class (`monitor/core/facade.py`)
Class `MonitorFacade` sẽ điều phối các adapter để cung cấp một điểm truy cập duy nhất.
```python
from typing import List, Any
from monitor.adapters.langsmith_adapter import LangSmithAdapter
from monitor.adapters.langfuse_adapter import LangfuseAdapter
from monitor.adapters.system_adapter import SystemAdapter

class MonitorFacade:
    def __init__(self):
        self.langsmith = LangSmithAdapter()
        self.langfuse = LangfuseAdapter()
        self.system = SystemAdapter()

    def get_tracing_callbacks(self) -> List[Any]:
        """
        Trả về danh sách gộp các callback từ cả LangSmith và Langfuse.
        Hỗ trợ dual-tracking (gửi telemetry đến cả 2 nền tảng cùng lúc).
        """
        callbacks = []
        if self.langsmith.is_enabled():
            callbacks.extend(self.langsmith.get_callbacks())
        if self.langfuse.is_enabled():
            callbacks.extend(self.langfuse.get_callbacks())
        return callbacks

    def log_system_resource(self, action: str, metadata: dict = None):
        """
        Ghi nhận thông số CPU/RAM và metadata tại thời điểm gọi.
        """
        self.system.log_usage(action, metadata)
```

### 3.2. Public Interface (`monitor/__init__.py`)
Các hàm được export ra bên ngoài để Core Agents có thể dễ dàng import.
```python
from monitor.core.facade import MonitorFacade

# Singleton instance
_facade = MonitorFacade()

def get_tracing_callbacks():
    """Lấy danh sách các LangChain callbacks cho monitor."""
    return _facade.get_tracing_callbacks()

def log_system_resource(action: str, metadata: dict = None):
    """Ghi nhận tài nguyên hệ thống (CPU/RAM)."""
    _facade.log_system_resource(action, metadata)
```

## 4. Chiến lược Mock dữ liệu ở Phase 1 (Data Mocking)
Do ở Phase 1 các Core Agents chưa hoàn thiện, module `monitor` sẽ sử dụng script `scripts/mock_simulator.py` để sinh dữ liệu giả lập và kiểm chứng Dual-Tracking.

**Cách triển khai:**
1. **Mock Agent Workflow:** Sử dụng cấu trúc LangChain/LangGraph cơ bản (ví dụ: `RunnableLambda` hoặc dummy `ChatOpenAI`) để giả lập luồng xử lý của Agent (e.g. OCR -> Chuẩn hóa -> So sánh).
2. **Inject Callbacks:** Truyền danh sách callback từ `get_tracing_callbacks()` vào tham số `config={"callbacks": ...}` của hàm `invoke`.
3. **Simulate Exceptions & Latency:** Trong các Dummy Node, thêm hàm `time.sleep()` ngẫu nhiên để tạo độ trễ (latency), hoặc chủ động `raise Exception` để kiểm tra khả năng bắt lỗi trên Dashboard của LangSmith và Langfuse.
4. **Simulate System Load:** Khởi tạo một mảng bộ nhớ lớn hoặc chạy vòng lặp tính toán để giả lập CPU/RAM spike, sau đó gọi hàm `log_system_resource()` để kiểm chứng ghi log.

## 5. File docker-compose.yml (Localhost Langfuse)
Dưới đây là file `docker-compose.yml` cơ bản nằm tại thư mục gốc của module `monitor` để dựng nhanh môi trường Langfuse UI và Database trên localhost cho Phase 1.

```yaml
version: '3.8'

services:
  langfuse-server:
    image: langfuse/langfuse:latest
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/postgres
      - NEXTAUTH_SECRET=mysecret # Đổi secret an toàn khi deploy thật
      - SALT=mysalt             # Đổi salt an toàn khi deploy thật
      - NEXTAUTH_URL=http://localhost:3000
      - TELEMETRY_ENABLED=false

  db:
    image: postgres:15
    restart: always
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=postgres
    ports:
      - "5432:5432"
    volumes:
      - langfuse_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  langfuse_data:
```
