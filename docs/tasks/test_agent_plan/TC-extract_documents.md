# Test Cases (Tinh gọn) — Node: `extract_documents` (test sau)

> **Node:** `src/agents/nodes/extract_documents.py::extract_documents`
> **Schema target:** `src/models_v1/quotation/extraction.py` (`ExtractionDraftPayload`, `ExtractedFieldValue`, `ExtractedItemField`, `FieldSource`)
> **Pipeline Contract:** `specs/contracts/pipeline.md` — Giai đoạn `UploadedDocument` → `DocumentRepresentation` → `ExtractionDraft`
> **Mục tiêu:** Kiểm tra khả năng tiếp nhận đầu ra từ OCR/LLM và đóng gói vào `state["raw_extractions"]` an toàn, chuẩn schema trước khi chuyển sang `ValidatedExtraction` và **HITL-1 bắt buộc**.
> **Trạng thái:** Tinh gọn (6 TC cốt lõi) — Chờ duyệt trước khi code.

---

## I. Schema Contract & Quy ước State

1. **Output của Node:**
   * Cập nhật `state["raw_extractions"]`: danh sách các trích xuất ứng với từng document đầu vào.
   * Mỗi bản ghi trích xuất thành công được serialize từ `ExtractionDraftPayload.model_dump(mode="json")`.
2. **Quy tắc trích xuất thô (Draft):**
   * Trường không có trong tài liệu trả `None` (hoặc `ExtractedFieldValue(value=None)`), **tuyệt đối không tự suy đoán**.
   * **Không** normalize đơn vị đo (UOM) hoặc tỷ giá tại node này (để node `Normalize` xử lý sau HITL-1).
   * Chuẩn hóa duy nhất tại node này: Mã tiền tệ `currency` viết hoa (`VND`, `USD`).
3. **Fault Isolation (Cách ly lỗi):**
   * Lỗi file không tồn tại, OCR không đọc được, hoặc LLM sinh lỗi schema -> Ghi nhận thông tin lỗi cho document đó, **tuyệt đối không raise exception làm crash pipeline**.

---

## II. Danh sách 6 Test Cases cốt lõi

### TC-01 — Happy Path: Trích xuất đầy đủ 1 báo giá & Field Provenance

* **Mục tiêu:** Kiểm tra trích xuất thành công 1 document đầy đủ trường thông tin, đúng schema `ExtractionDraftPayload`, bảo toàn tọa độ provenance (`FieldSource`).
* **Input State:**
  ```python
  state = {"documents": ["/uploads/vendor_a.pdf"]}
  # Mock OCR: Trả về văn bản báo giá hợp lệ của "Công ty ABC"
  # Mock LLM Extractor: Trả về ExtractionDraftPayload đầy đủ
  ```
* **Expected Output:**
  ```python
  assert len(result["raw_extractions"]) == 1
  draft = result["raw_extractions"][0]

  # Header fields
  assert draft["supplier_name"]["value"] == "Công ty ABC"
  assert draft["supplier_name"]["confidence"] == "0.95"  # hoặc Decimal("0.95")
  assert draft["currency"]["value"] == "VND"
  assert draft["vat_rate"]["value"] == "0.10"
  assert draft["vat_included"]["value"] is False
  assert draft["lead_time_days"]["value"] == "7"
  assert draft["warranty_months"]["value"] == "12"
  assert draft["payment_terms"]["value"] == "Thanh toán trong 30 ngày"

  # Line item
  assert len(draft["items"]) == 1
  item = draft["items"][0]
  assert item["source_item_id"] == "item-1"
  assert item["product_name"]["value"] == "Laptop Dell XPS 13"
  assert item["unit_price"]["value"] == "25000000.00"

  # Provenance tracking (FieldSource)
  assert item["product_name"]["source"]["document_id"] == "doc-1"
  assert item["product_name"]["source"]["page_number"] == 1
  assert item["product_name"]["source"]["block_id"] == "p1-b1"
  ```

---

### TC-02 — Multi-Document: Nhiều tài liệu từ nhiều nhà cung cấp

* **Mục tiêu:** Đảm bảo node xử lý danh sách nhiều file PDF và tạo ra các draft độc lập tương ứng trong `state["raw_extractions"]`.
* **Input State:**
  ```python
  state = {"documents": ["/uploads/vendor_a.pdf", "/uploads/vendor_b.pdf"]}
  # vendor_a.pdf -> Mock LLM trả về draft của NCC A (2 items)
  # vendor_b.pdf -> Mock LLM trả về draft của NCC B (1 item)
  ```
* **Expected Output:**
  ```python
  assert len(result["raw_extractions"]) == 2

  draft_a = result["raw_extractions"][0]
  assert draft_a["supplier_name"]["value"] == "Nhà cung cấp A"
  assert len(draft_a["items"]) == 2

  draft_b = result["raw_extractions"][1]
  assert draft_b["supplier_name"]["value"] == "Nhà cung cấp B"
  assert len(draft_b["items"]) == 1
  ```

---

### TC-03 — Multi-Items: Báo giá có nhiều dòng hàng trong 1 tài liệu

* **Mục tiêu:** Báo giá thực tế có bảng nhiều dòng hàng. Đảm bảo mọi dòng hàng đều được bóc tách vào `draft["items"]` với `source_item_id` phân biệt.
* **Input State:**
  ```python
  state = {"documents": ["/uploads/multi_items.pdf"]}
  # Mock LLM trả về draft với 3 items: Item 1 (Màn hình), Item 2 (Bàn phím), Item 3 (Chuột)
  ```
* **Expected Output:**
  ```python
  draft = result["raw_extractions"][0]
  assert len(draft["items"]) == 3

  item_ids = [it["source_item_id"] for it in draft["items"]]
  assert len(set(item_ids)) == 3  # Mỗi item có định danh duy nhất

  assert draft["items"][0]["product_name"]["value"] == "Màn hình Dell 27 inch"
  assert draft["items"][1]["product_name"]["value"] == "Bàn phím cơ Logitech"
  assert draft["items"][2]["product_name"]["value"] == "Chuột không dây MX Master"
  ```

---

### TC-04 — Missing/Optional Fields: Tài liệu thiếu thông tin (Không tự đoán)

* **Mục tiêu:** Theo Contract, nếu OCR/LLM không tìm thấy thông tin (`warranty_months`, `product_code`, `vat_rate`), giá trị phải là `None`, tuyệt đối không tự điền mặc định.
* **Input State:**
  ```python
  state = {"documents": ["/uploads/simple_quote.pdf"]}
  # Báo giá không ghi thời gian bảo hành và không có mã sản phẩm:
  # warranty_months = None
  # product_code = None
  # vat_rate = None nhưng vat_included = True
  ```
* **Expected Output:**
  ```python
  draft = result["raw_extractions"][0]

  assert draft["warranty_months"] is None
  assert draft["vat_rate"] is None
  assert draft["vat_included"]["value"] is True

  item = draft["items"][0]
  assert item["product_code"] is None
  assert item["product_name"]["value"] == "Máy in Canon"
  ```

---

### TC-05 — Currency Normalization: Chuẩn hóa mã tiền tệ viết hoa

* **Mục tiêu:** LLM thường trả về `"vnd"`, `"Vnd"`, hoặc `"usd"`. Node phải chuẩn hóa sang chữ in hoa (`VND`, `USD`) trong `ExtractedFieldValue`.
* **Input State:**
  ```python
  state = {"documents": ["/uploads/vendor_c.pdf"]}
  # Mock LLM trả về: currency = ExtractedFieldValue(value="vnd", confidence=Decimal("0.98"))
  ```
* **Expected Output:**
  ```python
  draft = result["raw_extractions"][0]
  assert draft["currency"]["value"] == "VND"  # Đã được uppercase
  assert draft["currency"]["confidence"] == "0.98"
  ```

---

### TC-06 — Fault Isolation: Cách ly lỗi file hỏng / OCR rỗng / LLM lỗi

* **Mục tiêu:** Đảm bảo tính kiên cố (resilience) của pipeline: Khi file không tồn tại, file trắng chữ (OCR ra chuỗi rỗng), hoặc LLM gặp sự cố parse, node **không ném exception crash workflow**, mà ghi nhận thông tin thất bại để chuyển tiếp.
* **Kịch bản test (Parameterized):**
  1. File không tồn tại trên disk (`/uploads/non_existent.pdf`).
  2. OCR quét ra văn bản rỗng (`""` hoặc chỉ whitespace).
  3. LLM trả về dữ liệu hỏng cấu trúc (không parse được Pydantic).
* **Expected Output chung:**
  ```python
  # Pipeline không dừng đột ngột
  assert "raw_extractions" in result
  assert len(result["raw_extractions"]) == 1

  record = result["raw_extractions"][0]
  # Bản ghi lỗi chứa tín hiệu rõ ràng để bước ValidatedExtraction hoặc HITL nhận diện
  assert record.get("status") == "failed" or record.get("extraction_error") is not None
  ```

---

## III. Ma trận kiểm soát chất lượng (6 nguyên tắc)

| Câu hỏi kiểm tra                                        | Đánh giá trên bộ 6 TC tinh gọn                                                                                                              |
| :--------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------ |
| **1. Assert cụ thể hay chỉ "không crash"?**      | Cụ thể 100%: Assert đúng giá trị nghiệp vụ (`"Công ty ABC"`, `"VND"`, `len == 3`, `None`), không dùng `is not None` mơ hồ. |
| **2. Expected độc lập hay copy logic?**           | Độc lập: Dựa trên payload mẫu nghiệp vụ định trước.                                                                                   |
| **3. Có mock quá mức không?**                    | Không: Chỉ mock 2 client ngoài (`ocr_client`, `extraction_client`), toàn bộ code logic của node chạy thật.                            |
| **4. Test behavior hay implementation?**             | 100% Test behavior: Input`state` → Output `state`. Không assert số lần gọi hàm hay method nội bộ.                                     |
| **5. Đổi toán tử / xóa dòng có đỏ không?** | Đỏ ngay: Xóa`.upper()` làm TC-05 đỏ; đổi mapping items làm TC-03 đỏ; tự gán default làm TC-04 đỏ.                               |
| **6. Đủ edge case thiết yếu không?**            | Đủ: Bao quát file thiếu trường, format bẩn chữ thường, file không tồn tại, OCR rỗng, multi-docs.                                    |
