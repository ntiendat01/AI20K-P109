# Model boundaries

`src/domain` chứa Pydantic schema và value contracts. Thư mục này không chứa ORM, database table hoặc repository.

## Canonical modules

- `agent/`: strict contracts consumed by LangGraph, HITL and deterministic
  analysis. This package replaces the former parallel `src/models_v1` root.
- `common.py`: base model và primitive dùng chung.
- `document.py`: uploaded document và OCR representation.
- `quotation/extraction.py`: machine output trước Buyer confirmation.
- `quotation/confirmation.py`: quotation payload đã được Buyer xác nhận.
- `analysis/normalization.py`: normalized quotation artifacts.
- `analysis/tco.py`: deterministic TCO artifacts.
- `analysis/risk.py`: risk-analysis artifacts.
- `analysis/comparison.py`: supplier-comparison artifacts.
- `analysis/decision.py`: Decision LLM proposal presented to Buyer HITL.
- `approval.py`: Buyer submission và Manager decision.
- `workflow.py`: analysis lifecycle, immutable artifacts và job progress.
- `purchase_request.py`, `purchase_order.py`: PR và PO business schemas.

## Dependency direction

```text
common/document/quotation
          ↓
       analysis
          ↓
       approval
          ↓
    purchase_order
```

Domain không được import API route, application workflow, repository hoặc LangGraph node. Pipeline node và application workflow import contract từ các module theo nghiệp vụ trong `src.domain`.

## Current contracts

- `procurement/contracts.py`: hợp đồng PR, báo giá, so sánh và PO của luồng procurement.
- `procurement/pipeline.py`: dữ liệu trích xuất, chuẩn hóa, TCO và đề xuất của ca mua sắm.
- `procurement/workflow.py`: trạng thái và kết quả workflow procurement.
- `analysis/evaluation.py`: proposal, bằng chứng và kết quả evaluation.

Graph và HITL import contract qua `src.domain.agent`; request/response chỉ phục vụ HTTP nằm trong `src.api.contracts`. Không tạo thêm model root song song hoặc package mang tên version.

Các contract được chuyển giữ nguyên field, validator và dạng JSON đang dùng; lần tái cấu trúc này chỉ đổi vị trí module.

Mỗi schema class phải có docstring ngay sau khai báo class, mô tả vai trò của class trong luồng nghiệp vụ.
