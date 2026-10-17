# Test Cases — Node: `human_review_extraction` (HITL-1)

> **Node:** `src/agents/nodes/human_review_extraction.py::human_review_extraction`**Schema target:**
>
> - `src/models_v1/quotation/confirmation.py` (`QuotationConfirmationRequest`, `ConfirmedItemPayload`)
> - `src/models_v1/quotation/extraction.py` (`ExtractionDraftPayload`, `ValidatedExtraction`)
>   **Pipeline Contract:** `specs/contracts/pipeline.md` (Phần HITL-1 — Buyer Confirmation bắt buộc)
>   **Đặc tính node:** LangGraph Interrupt Node (Tạm dừng workflow tại checkpoint `extraction_review`, chờ Buyer duyệt và trả về danh sách `QuotationConfirmationRequest`).
>   **Chiến lược Mock:** Chỉ mock duy nhất hàm `langgraph.types.interrupt` để giả lập Buyer tương tác resume state; toàn bộ logic Pydantic parsing, số lượng matching, và kiểm tra liên kết `source_item_id` chạy 100% code thật.
>   **Trạng thái:** Chờ duyệt — CHƯA viết code test.

---

## I. Nguyên tắc và Quy tắc Contract

1. **Cấu trúc Interrupt Payload (Dữ liệu gửi tới Buyer Review UI):**

   * Checkpoint định danh: `checkpoint = "extraction_review"`.
   * Chế độ review: `review_mode = "mandatory"`.
   * Danh sách drafts: `drafts` là list các dict đã dump từ `ExtractionDraftPayload`.
   * Danh sách kết quả kiểm tra validation: `validations` là list các dict dump từ `ValidatedExtraction`.
2. **Quy tắc Khớp số lượng Confirmation (`ConfirmationCountError`):**

   * Số lượng confirmation nhận được từ Buyer (`len(confirmations)`) phải **bằng chính xác** số lượng draft đầu vào (`len(drafts)`).
   * Nếu không khớp -> Bắn ngoại lệ `ConfirmationCountError(expected=..., actual=...)`.
3. **Quy tắc Liên kết Nguồn gốc Dòng hàng (`source_item_id` & `UnknownSourceItemError`):**

   * Mỗi draft có tập hợp `source_item_ids = {item.source_item_id for item in draft.items}`.
   * Với từng dòng hàng trong confirmation:
     * Nếu `item.source_item_id is not None`: Giá trị này **bắt buộc** phải thuộc tập `source_item_ids` của draft tương ứng. Nếu không thuộc -> Bắn ngoại lệ `UnknownSourceItemError`.
     * Nếu `item.source_item_id is None`: Đây là dòng hàng mới do Buyer chủ động bổ sung bằng tay trong phiên review -> Hợp lệ, chấp nhận.
4. **Quy tắc Schema Hợp lệ (`QuotationConfirmationRequest`):**

   * Response từ Buyer gửi lại phải tuân thủ nghiêm ngặt schema của `QuotationConfirmationRequest`:
     * Bắt buộc có: `supplier_name`, `currency`, `vat_rate`, `vat_included`, `lead_time_days`, `warranty_months`, `payment_terms`, và ít nhất 1 item trong `items`.
     * Không chứa chi phí vận chuyển (`shipping_cost` bị loại khỏi quotation contract).
     * Các trường tiền và số lượng định dạng chuẩn Decimal string.
5. **State Contract Đầu ra:**

   * Trả về dict: `{"confirmed_quotes": list[QuotationConfirmationRequest]}`.

---

## II. Danh sách Test Cases

### TC-01 — Happy Path: Buyer xác nhận 1 draft đơn lẻ hợp lệ hoàn hảo

* **Mục tiêu:** Kiểm tra luồng xác nhận thành công 1 báo giá: gọi `interrupt` với đúng payload, parse thành công response từ Buyer, bảo tồn `source_item_id`, và trả về `{"confirmed_quotes": [...]}`.
* **Input State:**
  ```python
  state = {
      "raw_extractions": [sample_valid_draft_dict],
      "validated_extractions": [sample_validated_extraction],
  }
  ```
* **Giả lập `interrupt` response:**
  ```python
  buyer_response = [
      {
          "supplier_name": "Công ty ABC",
          "currency": "VND",
          "vat_rate": "0.10",
          "vat_included": True,
          "lead_time_days": 7,
          "warranty_months": 12,
          "payment_terms": "30 ngày",
          "items": [
              {
                  "source_item_id": "item-1",
                  "product_name": "Laptop Dell Core i7",
                  "product_code": "DELL-5520",
                  "unit": "cái",
                  "quantity": "2",
                  "unit_price": "20000000.00",
              }
          ],
          "review_note": "Đã thương lượng bảo hành",
      }
  ]
  ```
* **Expected Output:**
  ```python
  # 1. interrupt được gọi đúng 1 lần với payload chuẩn:
  mock_interrupt.assert_called_once_with(
      {
          "checkpoint": "extraction_review",
          "review_mode": "mandatory",
          "drafts": [draft_payload_dict],
          "validations": [val_dict],
      }
  )

  # 2. State trả về:
  assert "confirmed_quotes" in result
  assert len(result["confirmed_quotes"]) == 1
  confirmed = result["confirmed_quotes"][0]
  assert isinstance(confirmed, QuotationConfirmationRequest)
  assert confirmed.supplier_name == "Công ty ABC"
  assert confirmed.currency == "VND"
  assert confirmed.items[0].source_item_id == "item-1"
  assert confirmed.items[0].quantity == Decimal("2")
  assert confirmed.items[0].unit_price == Decimal("20000000.00")
  assert confirmed.review_note == "Đã thương lượng bảo hành"
  ```

---

### TC-02 — Buyer Manual Addition: Buyer thêm mới dòng hàng bằng tay (`source_item_id = None`)

* **Mục tiêu:** Kiểm tra tính năng cho phép Buyer bổ sung item thủ công trong lúc review. Item mới không có trong OCR nên `source_item_id = None`. Node phải chấp nhận hợp lệ và không bắn lỗi `UnknownSourceItemError`.
* **Input State:** 1 draft có item `source_item_id="item-1"`.
* **Giả lập `interrupt` response:**
  ```python
  buyer_response = [
      {
          "supplier_name": "Công ty ABC",
          "currency": "VND",
          "vat_rate": "0.10",
          "vat_included": True,
          "lead_time_days": 5,
          "warranty_months": 24,
          "payment_terms": "Chuyển khoản",
          "items": [
              {
                  "source_item_id": "item-1",  # Item gốc OCR
                  "product_name": "Server Dell R740",
                  "unit": "bộ",
                  "quantity": "1",
                  "unit_price": "80000000.00",
              },
              {
                  "source_item_id": None,  # Item Buyer bổ sung thêm thủ công
                  "product_name": "Gói cài đặt & bảo trì 1 năm",
                  "unit": "gói",
                  "quantity": "1",
                  "unit_price": "5000000.00",
              },
          ],
      }
  ]
  ```
* **Expected Output:**
  ```python
  assert len(result["confirmed_quotes"]) == 1
  items = result["confirmed_quotes"][0].items
  assert len(items) == 2
  assert items[0].source_item_id == "item-1"
  assert items[1].source_item_id is None
  assert items[1].product_name == "Gói cài đặt & bảo trì 1 năm"
  ```

---

### TC-03 — Payload Contract: Kiểm tra tính toàn vẹn của dữ liệu gửi vào `interrupt`

* **Mục tiêu:** Đảm bảo node serialize đầy đủ cả `drafts` và `validations` từ State sang định dạng json-serializable dict, gán đúng `checkpoint="extraction_review"` và `review_mode="mandatory"` để FE HITL-1 hiển thị đầy đủ thông tin cảnh báo/issue cho Buyer.
* **Input State:** State có 1 draft thô và 1 validation có 1 warning (`LOW_CONFIDENCE`).
* **Expected Output:**
  ```python
  call_args = mock_interrupt.call_args[0][0]
  assert call_args["checkpoint"] == "extraction_review"
  assert call_args["review_mode"] == "mandatory"
  assert len(call_args["drafts"]) == 1
  assert len(call_args["validations"]) == 1
  assert call_args["validations"][0]["schema_valid"] is True
  assert call_args["validations"][0]["issues"][0]["code"] == "LOW_CONFIDENCE"
  ```

---

### TC-04 — Confirmation Count Mismatch: Lệch số lượng confirmation vs drafts

* **Mục tiêu:**
  1. Có 2 draft nhưng Buyer chỉ gửi xác nhận 1 -> Raise `ConfirmationCountError(expected=2, actual=1)`.
  2. Có 1 draft nhưng response trả về 2 confirmation -> Raise `ConfirmationCountError(expected=1, actual=2)`.
* **Input State:**
  * Trường hợp 1: `len(raw_extractions) == 2`.
  * Response: List có 1 phần tử.
* **Expected Output:**
  ```python
  with pytest.raises(ConfirmationCountError) as exc_info:
      human_review_extraction(state)
  assert exc_info.value.expected == 2
  assert exc_info.value.actual == 1
  assert "Expected 2 quotation confirmations, received 1" in str(exc_info.value)
  ```

---

### TC-05 — Lineage Violation: Dòng hàng mang `source_item_id` lạ không thuộc draft

* **Mục tiêu:** Ngăn chặn lỗi lẫn lộn hoặc giả mạo ID dòng hàng giữa các draft hoặc từ ngoài vào. Nếu `source_item_id` không rỗng nhưng không nằm trong danh sách item của draft tương ứng -> Phải raise `UnknownSourceItemError`.
* **Input State:** Draft có item với `source_item_id="item-A"`.
* **Giả lập `interrupt` response:** Buyer response chứa item có `source_item_id="item-UNKNOWN-999"`.
* **Expected Output:**
  ```python
  with pytest.raises(UnknownSourceItemError) as exc_info:
      human_review_extraction(state)
  assert exc_info.value.source_item_id == "item-UNKNOWN-999"
  assert "Confirmed source item does not belong to its extraction draft: item-UNKNOWN-999" in str(exc_info.value)
  ```

---

### TC-06 — Invalid Confirmation Schema: Response không thỏa mãn schema Pydantic

* **Mục tiêu:** Kiểm tra khi Buyer response bị thiếu trường bắt buộc (ví dụ thiếu `vat_rate`, thiếu `payment_terms`, hoặc `items=[]`), Pydantic `ValidationError` phải được kích hoạt từ `CONFIRMATION_LIST_ADAPTER.validate_python`.
* **Input State:** 1 draft hợp lệ.
* **Giả lập `interrupt` response:**
  ```python
  # Thiếu items (bắt buộc min_length=1) và thiếu vat_rate
  buyer_response = [
      {
          "supplier_name": "Công ty ABC",
          "currency": "VND",
          # Thiếu vat_rate
          "vat_included": True,
          "lead_time_days": 7,
          "warranty_months": 12,
          "payment_terms": "30 ngày",
          "items": [],  # Sai: min_length=1
      }
  ]
  ```
* **Expected Output:**
  ```python
  with pytest.raises(ValidationError) as exc_info:
      human_review_extraction(state)
  errors = exc_info.value.errors()
  field_paths = [".".join(str(p) for p in err["loc"]) for err in errors]
  assert any("vat_rate" in p for p in field_paths)
  assert any("items" in p for p in field_paths)
  ```

---

### TC-07 — Multiple Drafts Correspondence: Xử lý nhiều báo giá đồng thời đúng thứ tự

* **Mục tiêu:** Khi workflow xử lý cùng lúc 2 báo giá (ví dụ NCC 1 và NCC 2), hàm kiểm tra đúng thứ tự từng cặp `(draft_1, conf_1)` và `(draft_2, conf_2)`. Item của draft 1 không được gán nhầm sang draft 2 và ngược lại.
* **Input State:**
  * Draft 1 có item `"item-A1"`.
  * Draft 2 có item `"item-B1"`.
* **Giả lập `interrupt` response:**
  * Conf 1 tương ứng Draft 1, item `"item-A1"`.
  * Conf 2 tương ứng Draft 2, item `"item-B1"`.
* **Expected Output:**
  ```python
  result = human_review_extraction(state)
  assert len(result["confirmed_quotes"]) == 2
  assert result["confirmed_quotes"][0].supplier_name == "NCC 1"
  assert result["confirmed_quotes"][0].items[0].source_item_id == "item-A1"
  assert result["confirmed_quotes"][1].supplier_name == "NCC 2"
  assert result["confirmed_quotes"][1].items[0].source_item_id == "item-B1"
  ```

  *(Nếu tráo đổi thứ tự item của conf 2 sang conf 1 -> lập tức bắn `UnknownSourceItemError`).*

---

### TC-08 — Empty State Handling: Danh sách drafts rỗng

* **Mục tiêu:** Khi `raw_extractions = []`, interrupt vẫn được gọi với `drafts = []`, response là `[]`, và kết quả trả về `{"confirmed_quotes": []}` an toàn, không crash.
* **Input State:** `state = {"raw_extractions": [], "validated_extractions": []}`.
* **Giả lập `interrupt` response:** `[]`.
* **Expected Output:**
  ```python
  result = human_review_extraction(state)
  assert result["confirmed_quotes"] == []
  mock_interrupt.assert_called_once_with(
      {
          "checkpoint": "extraction_review",
          "review_mode": "mandatory",
          "drafts": [],
          "validations": [],
      }
  )
  ```

---

## III. Ma trận đánh giá theo 6 nguyên tắc kiểm thử

| Nguyên tắc                                               | Đánh giá bộ test`human_review_extraction`                                                                                                                                                                                                   |
| :--------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **1. Assert cụ thể hay không crash?**             | Cụ thể 100%: Assert từng field của payload gọi interrupt, kiểu trả về`QuotationConfirmationRequest`, từng thuộc tính Decimal, thông điệp ngoại lệ và giá trị `expected`/`actual` của `ConfirmationCountError`.        |
| **2. Expected độc lập hay copy logic?**           | Độc lập: Dữ liệu test dựng sẵn theo hợp đồng API confirmation (`QuotationConfirmationRequest`), không phụ thuộc vào code implementation.                                                                                          |
| **3. Có mock quá mức không?**                    | **Mock tối thiểu (Chỉ 1 hàm):** Chỉ mock duy nhất `langgraph.types.interrupt` vì đây là điểm ngắt framework. 100% logic TypeAdapter Pydantic, so khớp số lượng, và kiểm tra `source_item_id` chạy trên code thật. |
| **4. Test behavior hay implementation?**             | Hoàn toàn theo Behavior: State In (`raw_extractions`, `validated_extractions`) -> Interrupt Payload & State Out (`confirmed_quotes`).                                                                                                     |
| **5. Đổi toán tử / xóa dòng có đỏ không?** | Đỏ ngay lập tức: Xóa`ConfirmationCountError` -> TC-04 đỏ; Xóa check `UnknownSourceItemError` -> TC-05 đỏ; Đổi `source_item_id is not None` thành `is None` -> TC-02 đỏ; Sửa checkpoint payload -> TC-01 & TC-03 đỏ.     |
| **6. Đủ edge case thiết yếu không?**            | Đủ: Item do Buyer thêm mới (`source_item_id = None`), item lạ (`UnknownSourceItemError`), lệch số lượng xác nhận (thừa/thiếu), sai schema Pydantic, danh sách rỗng, nhiều draft song song.                                    |
