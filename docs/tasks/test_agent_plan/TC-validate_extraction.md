# Test Cases — Node: `validate_extraction`

> **Node:** `src/agents/nodes/validate_extraction.py::validate_extraction`
> **Schema target:** `src/models_v1/quotation/extraction.py` (`ValidatedExtraction`, `ValidationIssue`, `ValidationSeverity`)
> **Pipeline Contract:** `specs/contracts/pipeline.md` (Phần Extraction Validator — Ngưỡng toàn cục `0.80`)
> **Đặc tính node:** Pure validation logic (không có I/O ngoài, không cần mock, chạy 100% code thật).
> **Trạng thái:** Chờ duyệt — CHƯA viết code test.

---

## I. Nguyên tắc và Quy tắc Contract

1. **Ngưỡng tin cậy toàn cục:** `CONFIDENCE_THRESHOLD = Decimal("0.80")`
   * `confidence >= 0.80`: Đạt chuẩn, không cảnh báo.
   * `confidence < 0.80`: Tạo `ValidationIssue(code="LOW_CONFIDENCE", severity=WARNING)`.
2. **Nguồn gốc dữ liệu (Provenance):**
   * Nếu `field.source is None`: Tạo `ValidationIssue(code="MISSING_PROVENANCE", severity=WARNING)`.
3. **Mức độ nghiêm trọng & Schema Valid:**
   * `BLOCKING`: Thiếu trường bắt buộc (`supplier_name`, `currency`, `items`, `items[i].product_name`, `items[i].unit`, `items[i].quantity`, `items[i].unit_price`) hoặc sai schema Pydantic.
   * `schema_valid = False` khi và chỉ khi có ít nhất 1 issue mang mức độ `BLOCKING`.
   * Cảnh báo `WARNING` không làm `schema_valid = False`.
4. **State Contract:**
   * Node nhận `state["raw_extractions"]: list[dict]`.
   * Node trả về `{"validated_extractions": list[dict], "review_mode": "mandatory"}`.

---

## II. Danh sách Test Cases

### TC-01 — Happy Path: Draft hợp lệ hoàn hảo, không có bất kỳ issue nào

* **Mục tiêu:** Kiểm tra khi draft có đầy đủ mọi trường bắt buộc, confidence đều >= 0.80, có source đầy đủ thì kết quả `schema_valid = True` và danh sách `issues` rỗng.
* **Input State:**
  ```python
  state = {
      "raw_extractions": [
          {
              "supplier_name": {"value": "Công ty ABC", "confidence": "0.95", "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"}},
              "currency": {"value": "VND", "confidence": "0.99", "source": {"document_id": "d1", "page_number": 1, "block_id": "b2"}},
              "vat_rate": {"value": "0.10", "confidence": "0.90", "source": {"document_id": "d1", "page_number": 1, "block_id": "b3"}},
              "items": [
                  {
                      "source_item_id": "item-1",
                      "product_name": {"value": "Laptop Dell", "confidence": "0.92", "source": {"document_id": "d1", "page_number": 1, "block_id": "b4"}},
                      "unit": {"value": "cái", "confidence": "0.90", "source": {"document_id": "d1", "page_number": 1, "block_id": "b5"}},
                      "quantity": {"value": "2", "confidence": "0.95", "source": {"document_id": "d1", "page_number": 1, "block_id": "b6"}},
                      "unit_price": {"value": "20000000.00", "confidence": "0.91", "source": {"document_id": "d1", "page_number": 1, "block_id": "b7"}},
                  }
              ]
          }
      ]
  }
  ```
* **Expected Output:**
  ```python
  assert result["review_mode"] == "mandatory"
  assert len(result["validated_extractions"]) == 1

  val = result["validated_extractions"][0]
  assert val["schema_valid"] is True
  assert val["human_confirmation_required"] is True
  assert val["issues"] == []
  ```

---

### TC-02 — Boundary Confidence: Kiểm tra chính xác tại ngưỡng 0.80

* **Mục tiêu:** Kiểm thử tính đúng đắn của toán tử so sánh `< 0.80` tại các điểm biên: `0.80` (đạt) vs `0.79` (cảnh báo).
* **Input State:**
  ```python
  # Draft A: supplier_name có confidence = Decimal("0.80") (ngay tại biên)
  # Draft B: supplier_name có confidence = Decimal("0.79") (dưới biên 0.01)
  ```
* **Expected Output:**
  ```python
  # Với Draft A (0.80):
  val_a = result["validated_extractions"][0]
  low_conf_issues_a = [i for i in val_a["issues"] if i["code"] == "LOW_CONFIDENCE"]
  assert low_conf_issues_a == []  # 0.80 không bị phạt warning

  # Với Draft B (0.79):
  val_b = result["validated_extractions"][1]
  assert val_b["schema_valid"] is True  # Warning không làm invalid schema
  assert len(val_b["issues"]) == 1
  issue = val_b["issues"][0]
  assert issue["field_path"] == "supplier_name"
  assert issue["code"] == "LOW_CONFIDENCE"
  assert issue["severity"] == "warning"
  assert issue["confidence"] == "0.79"  # Decimal("0.79")
  ```

---

### TC-03 — Missing Provenance: Có giá trị nhưng thiếu nguồn gốc (source = None)

* **Mục tiêu:** Trường có giá trị và độ tin cậy cao (`0.95`) nhưng `source is None` -> Phải sinh warning `MISSING_PROVENANCE`.
* **Input State:**
  ```python
  # Draft có items[0].unit_price có source = None
  state = {
      "raw_extractions": [
          {
              "supplier_name": {"value": "NCC X", "confidence": "0.90", "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"}},
              "currency": {"value": "VND", "confidence": "0.90", "source": {"document_id": "d1", "page_number": 1, "block_id": "b2"}},
              "items": [
                  {
                      "source_item_id": "item-1",
                      "product_name": {"value": "Màn hình", "confidence": "0.90", "source": {"document_id": "d1", "page_number": 1, "block_id": "b3"}},
                      "unit": {"value": "cái", "confidence": "0.90", "source": {"document_id": "d1", "page_number": 1, "block_id": "b4"}},
                      "quantity": {"value": "1", "confidence": "0.90", "source": {"document_id": "d1", "page_number": 1, "block_id": "b5"}},
                      "unit_price": {"value": "5000000.00", "confidence": "0.95", "source": None},  # Thiếu source
                  }
              ]
          }
      ]
  }
  ```
* **Expected Output:**
  ```python
  val = result["validated_extractions"][0]
  assert val["schema_valid"] is True  # Warning không chặn confirm
  assert len(val["issues"]) == 1

  issue = val["issues"][0]
  assert issue["field_path"] == "items[0].unit_price"
  assert issue["code"] == "MISSING_PROVENANCE"
  assert issue["severity"] == "warning"
  ```

---

### TC-04 — Missing Required Fields: Thiếu trường bắt buộc ở Header & Item

* **Mục tiêu:** Thiếu trường bắt buộc (`supplier_name = None` hoặc chuỗi trắng `"   "`) -> Phải tạo issue `BLOCKING` và làm `schema_valid = False`.
* **Input State:**
  ```python
  # Draft thiếu supplier_name (None) và items[0].product_name có value là khoảng trắng "   "
  state = {
      "raw_extractions": [
          {
              "supplier_name": None,  # Thiếu bắt buộc
              "currency": {"value": "VND", "confidence": "0.90", "source": {...}},
              "items": [
                  {
                      "source_item_id": "item-1",
                      "product_name": {"value": "   ", "confidence": "0.90", "source": {...}},  # Rỗng sau strip
                      "unit": {"value": "cái", "confidence": "0.90", "source": {...}},
                      "quantity": {"value": "1", "confidence": "0.90", "source": {...}},
                      "unit_price": {"value": "1000.00", "confidence": "0.90", "source": {...}},
                  }
              ]
          }
      ]
  }
  ```
* **Expected Output:**
  ```python
  val = result["validated_extractions"][0]
  assert val["schema_valid"] is False  # Có issue blocking

  blocking_paths = [i["field_path"] for i in val["issues"] if i["severity"] == "blocking"]
  assert "supplier_name" in blocking_paths
  assert "items[0].product_name" in blocking_paths

  for issue in val["issues"]:
      if issue["field_path"] in ("supplier_name", "items[0].product_name"):
          assert issue["code"] == "MISSING_REQUIRED_FIELD"
  ```

---

### TC-05 — Empty Items List: Danh sách items rỗng

* **Mục tiêu:** Báo giá không có dòng hàng nào (`items = []`) -> Phải sinh issue blocking `MISSING_ITEMS` và `schema_valid = False`.
* **Input State:**
  ```python
  state = {
      "raw_extractions": [
          {
              "supplier_name": {"value": "NCC A", "confidence": "0.90", "source": {...}},
              "currency": {"value": "VND", "confidence": "0.90", "source": {...}},
              "items": []  # Không có item nào
          }
      ]
  }
  ```
* **Expected Output:**
  ```python
  val = result["validated_extractions"][0]
  assert val["schema_valid"] is False

  item_issues = [i for i in val["issues"] if i["field_path"] == "items"]
  assert len(item_issues) == 1
  assert item_issues[0]["code"] == "MISSING_ITEMS"
  assert item_issues[0]["severity"] == "blocking"
  ```

---

### TC-06 — Optional Fields: Trường tùy chọn bị thiếu không tạo issue

* **Mục tiêu:** `warranty_months = None`, `payment_terms = None`, `items[0].product_code = None` không được tạo issue. Nhưng nếu có giá trị mà `confidence < 0.80`, vẫn cảnh báo `LOW_CONFIDENCE`.
* **Input State:**
  ```python
  # warranty_months = None (không có trong tài liệu)
  # payment_terms = {value: "30 ngày", confidence: 0.65} (có nhưng confidence thấp)
  ```
* **Expected Output:**
  ```python
  val = result["validated_extractions"][0]
  assert val["schema_valid"] is True

  # Không có issue nào cho warranty_months
  assert not any(i["field_path"] == "warranty_months" for i in val["issues"])

  # Có issue LOW_CONFIDENCE cho payment_terms
  pt_issue = next(i for i in val["issues"] if i["field_path"] == "payment_terms")
  assert pt_issue["code"] == "LOW_CONFIDENCE"
  assert pt_issue["severity"] == "warning"
  assert pt_issue["confidence"] == "0.65"
  ```

---

### TC-07 — Pydantic Schema Failure: Dict đầu vào vỡ cấu trúc không parse được

* **Mục tiêu:** Khi dữ liệu thô trong `raw_extractions` bị lỗi cấu trúc nghiêm trọng (ví dụ: `items` không phải list mà là int, hoặc thiếu kiểu dữ liệu Pydantic cơ bản), hàm bắt `ValidationError` và chuyển hóa thành `schema_valid = False`, `code = "SCHEMA_INVALID"`. Không crash node.
* **Input State:**
  ```python
  state = {
      "raw_extractions": [
          {"items": "đây không phải là list"}  # Sai kiểu hoàn toàn
      ]
  }
  ```
* **Expected Output:**
  ```python
  val = result["validated_extractions"][0]
  assert val["schema_valid"] is False

  assert len(val["issues"]) >= 1
  assert any(i["code"] == "SCHEMA_INVALID" and i["severity"] == "blocking" for i in val["issues"])
  ```

---

### TC-08 — Multiple Drafts & Empty State: Xử lý nhiều draft độc lập và danh sách rỗng

* **Mục tiêu:**
  1. `state["raw_extractions"] = []` -> Trả về `validated_extractions = []`, `review_mode = "mandatory"`.
  2. Xử lý nhiều draft cùng lúc (Draft 1 hợp lệ, Draft 2 có lỗi) -> Trả về đúng 2 phần tử độc lập, không lẫn lộn kết quả giữa các draft.
* **Input State:**
  ```python
  state = {
      "raw_extractions": [valid_draft, invalid_draft]
  }
  ```
* **Expected Output:**
  ```python
  assert len(result["validated_extractions"]) == 2
  assert result["validated_extractions"][0]["schema_valid"] is True
  assert result["validated_extractions"][1]["schema_valid"] is False
  ```

---

## III. Ma trận đánh giá theo 6 nguyên tắc

| Câu hỏi                                                  | Đánh giá bộ test`validate_extraction`                                                                                                                       |
| :--------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Assert cụ thể hay không crash?**             | Cụ thể 100%: Assert chính xác từng`field_path`, `code` (`"LOW_CONFIDENCE"`, `"MISSING_REQUIRED_FIELD"`), `severity`, `confidence`.               |
| **2. Expected độc lập hay copy logic?**           | Độc lập: Dựa trên rule nghiệp vụ contract (ngưỡng 0.80, bắt buộc vs tùy chọn).                                                                       |
| **3. Có mock quá mức không?**                    | **0% Mock**: Node là pure validation function, test chạy 100% code thật của `validate_extraction.py`.                                                 |
| **4. Test behavior hay implementation?**             | Behavior: Input`state` → Output `state`. Không assert hàm nội bộ `_validate_draft` hay `_field_issues`.                                              |
| **5. Đổi toán tử / xóa dòng có đỏ không?** | Đỏ ngay lập tức: Đổi`<` thành `<=` ở ngưỡng 0.80 -> TC-02 đỏ; xóa check source -> TC-03 đỏ; đổi `BLOCKING` sang `WARNING` -> TC-04 đỏ. |
| **6. Đủ edge case thiết yếu không?**            | Đủ: Biên 0.80 vs 0.79, chuỗi rỗng sau strip`"   "`, list rỗng `items=[]`, draft rỗng, sai kiểu schema.                                                |
