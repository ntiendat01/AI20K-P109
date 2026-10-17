# Optimization v3 — Model Consolidation

## Kết luận

Tất cả Pydantic model hiện nằm dưới một root duy nhất: `src/models`.
Package song song `src/models_v1` và alias top-level `models_v1` đã được xóa.

Các strict contract của LangGraph/HITL nằm trong `src/models/agent`. Tên
`agent` biểu đạt boundary nghiệp vụ, không phải version. API/application model
tiếp tục nằm trong các module domain trực tiếp dưới `src/models`; implementation
legacy còn được cô lập trong `src/models/old` và các bridge hiện hữu.

## Mapping

| Boundary | Canonical path |
| --- | --- |
| Extraction và HITL-1 | `src.models.agent.quotation` |
| Normalization, TCO, comparison, risk | `src.models.agent.analysis` |
| Decision và HITL-2 | `src.models.agent.analysis.decision`, `src.models.agent.approval` |
| Agent state/workflow | `src.models.agent.workflow` |
| API/application model | Các module domain trực tiếp dưới `src.models` |
| Legacy bridge | `src.models.old` |

## Invariants

1. Không tạo model root song song với `src/models`.
2. Không đặt version trong Python package name; version thuộc API hoặc payload.
3. Agent node/tool chỉ import strict contract từ `src.models.agent`.
4. Payload/checkpoint giữ nguyên field, enum và validation; thay đổi này chỉ đổi
   module path nội bộ.
5. Chỉ gỡ bridge trong `src.models.old` khi API contract và persisted payload đã
   được migrate riêng.

## Kiểm chứng

- `rg 'src.models_v1|from models_v1|import models_v1' src tests scripts` không
  được trả kết quả.
- Contract tests của extraction, analysis, decision và HITL phải pass.
- Import smoke test phải load được `src.models.agent` và toàn bộ submodule.
