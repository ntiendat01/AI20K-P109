# Model boundaries

`src/models` chứa Pydantic schema và value contracts. Thư mục này không chứa ORM, database table hoặc repository.

## Canonical modules

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

Schema không được import API route, service, repository hoặc LangGraph node. Pipeline node và service import schema canonical, không thêm import mới từ `schemas.py`, `procurement.py` hoặc `evaluation.py`.

## Transition policy

Toàn bộ implementation legacy nằm trong `old/`. Các file `schemas.py`, `procurement.py`, `evaluation.py`, `pr.py`, `extracted_quotation.py` và `procurement_workflow.py` ở thư mục gốc chỉ là import bridge trong thời gian chuyển đổi. Schema canonical phải tự khai báo field/validator và tuyệt đối không import hay kế thừa schema legacy. Không thêm schema nghiệp vụ mới vào `old/` hoặc các bridge.

Chỉ xóa compatibility class sau khi:

1. không còn runtime import;
2. API contract và test đã chuyển sang canonical schema;
3. payload JSON cũ vẫn parse được hoặc đã có adapter rõ ràng.

Mỗi schema class phải có docstring ngay sau khai báo class, mô tả vai trò của class trong luồng nghiệp vụ.
