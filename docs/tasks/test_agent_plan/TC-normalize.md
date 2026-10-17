# Test Cases — Node: `normalize` (Data Normalization)

> **Node:** `src/agents/nodes/normalize.py::normalize`  
> **Schema target:**  
> - `src/models_v1/analysis/normalization.py` (`NormalizedQuotationArtifact`, `NormalizedItem`, `NormalizationStatus`)  
> - `src/models_v1/quotation/confirmation.py` (`QuotationConfirmationRequest`, `ConfirmedItemPayload`)  
> **Pipeline Contract:** `specs/contracts/pipeline.md` (Phần Normalizer — Chuẩn hóa định lượng UOM và FX)  
> **Đặc tính node:** Pure deterministic calculation node (100% logic tính toán số học và bảng tra cứu, không có LLM hay I/O ngoài, 0% Mock).  
> **Nguyên tắc kiểm thử:** **CHỈ ASSERT Ở BIÊN (State In -> State Out)**, tuyệt đối không assert hàm private (`_uom_factor`, `_currency_rate`, `_rule_id`).  
> **Trạng thái:** Chờ duyệt — CHƯA viết code test.

---

## I. Nguyên tắc và Quy tắc Contract

1. **State Contract Đầu vào & Đầu ra:**
   * **Input State:**
     * `state["confirmed_quotes"]: list[QuotationConfirmationRequest]` (Bắt buộc).
     * `state["pr_data"]: dict[str, Any]` chứa mục tiêu chuẩn hóa `target_uom` (mặc định `"cái"`) và `target_currency` (mặc định `"VND"`).
     * `state["case_id"]: str` (để tạo revision ID ổn định).
     * `state["normalization_rule_version"]: str` (mặc định `"uom-fx-v1"`).
   * **Output State:**
     * `{"normalized_quotes": list[NormalizedQuotationArtifact]}`.

2. **Công thức Chuẩn hóa Nghiệp vụ:**
   * **Quy đổi UOM (Đơn vị tính):**
     * Tra cứu hệ số quy đổi: `uom_factor = base_source / base_target` (qua `UOM_CONVERSION_TABLE`).
     * Số lượng chuẩn hóa: `normalized_quantity = source_quantity * uom_factor`.
     * Đơn giá sau quy đổi UOM: `unit_price_after_uom = source_unit_price / uom_factor`.
     *(Ví dụ: 1 hộp = 10 cái. Mua 2 hộp giá 100.000đ/hộp -> Chuẩn hóa: 20 cái, đơn giá 10.000đ/cái).*
   * **Quy đổi FX (Tiền tệ):**
     * Tra cứu tỷ giá: `fx_rate = source_rate_to_vnd / target_rate_to_vnd` (qua `FX_RATES_TO_VND`).
     * Đơn giá sau quy đổi FX: `normalized_unit_price = (unit_price_after_uom * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`.
   * **Định danh quy tắc (Rule ID):**
     * `rule_id = "uom:{source_uom}->{target_uom};fx:{source_currency}->{target_currency}"`.

3. **Bất biến Contract khi Thiếu Mapping (`NEEDS_MAPPING`):**
   * Nếu UOM không cùng loại cơ sở (ví dụ `kg` sang `cái`) hoặc không có trong bảng tra cứu -> Ghi nhận issue:  
     `"items[{i}]: missing UOM mapping '{source_uom}' -> '{target_uom}'"`
   * Nếu tiền tệ không có trong bảng tỷ giá (ví dụ `AUD` sang `VND`) -> Ghi nhận issue:  
     `"items[{i}]: missing FX rate '{source_currency}' -> '{target_currency}'"`
   * **Bất biến (Invariant):** Khi có bất kỳ issue nào ở dòng hàng, các trường chuẩn hóa của dòng đó **BẮT BUỘC LÀ `None`**:
     * `normalized_quantity = None`
     * `normalized_uom = None`
     * `normalized_unit_price = None`
     * `normalized_currency = None`
     * `rule_id = None`
     * *(Tuyệt đối không đoán mò, không tự động sao chép giá trị gốc).*
   * **Trạng thái Artifact:**
     * Không có issue nào -> `status = NormalizationStatus.NORMALIZED`.
     * Có ít nhất 1 issue -> `status = NormalizationStatus.NEEDS_MAPPING`.

---

## II. Danh sách Test Cases

### TC-01 — Identity Normalization: Cùng UOM và Cùng Tiền tệ (Không thay đổi giá trị)
* **Mục tiêu:** Kiểm tra khi báo giá đã đúng `target_uom` ("cái") và `target_currency` ("VND") thì số lượng và đơn giá giữ nguyên 100%, status là `NORMALIZED`, `issues == []`.
* **Input State:**
  ```python
  state = {
      "pr_data": {"target_uom": "cái", "target_currency": "VND"},
      "confirmed_quotes": [
          QuotationConfirmationRequest(
              supplier_name="NCC A",
              currency="VND",
              vat_rate=Decimal("0.10"),
              vat_included=True,
              lead_time_days=7,
              warranty_months=12,
              payment_terms="30 ngày",
              items=[
                  ConfirmedItemPayload(
                      product_name="Chuột máy tính",
                      unit="cái",
                      quantity=Decimal("5"),
                      unit_price=Decimal("150000.00"),
                  )
              ],
          )
      ],
  }
  ```
* **Expected Output ở Biên:**
  ```python
  artifact = result["normalized_quotes"][0]
  assert artifact.status == NormalizationStatus.NORMALIZED
  assert artifact.issues == []
  item = artifact.items[0]
  assert item.normalized_quantity == Decimal("5")
  assert item.normalized_uom == "cái"
  assert item.normalized_unit_price == Decimal("150000.00")
  assert item.normalized_currency == "VND"
  assert item.rule_id == "uom:cái->cái;fx:VND->VND"
  ```

---

### TC-02 — UOM Conversion: Quy đổi Đơn vị tính (Hộp sang Cái)
* **Mục tiêu:** Kiểm tra phép toán quy đổi UOM: 1 hộp = 10 cái. Mua 3 hộp đơn giá 200.000đ/hộp -> Chuẩn hóa thành 30 cái, đơn giá 20.000đ/cái.
* **Input State:**
  * `pr_data`: `target_uom="cái"`, `target_currency="VND"`.
  * `confirmed_quotes`: 1 quote, currency="VND", item: `unit="hộp"`, `quantity=Decimal("3")`, `unit_price=Decimal("200000.00")`.
* **Expected Output ở Biên:**
  ```python
  artifact = result["normalized_quotes"][0]
  assert artifact.status == NormalizationStatus.NORMALIZED
  item = artifact.items[0]
  assert item.source_quantity == Decimal("3")
  assert item.source_unit_price == Decimal("200000.00")
  assert item.normalized_quantity == Decimal("30")
  assert item.normalized_uom == "cái"
  assert item.normalized_unit_price == Decimal("20000.00")
  assert item.rule_id == "uom:hộp->cái;fx:VND->VND"
  ```

---

### TC-03 — FX Conversion: Quy đổi Tiền tệ (USD sang VND)
* **Mục tiêu:** Kiểm tra phép nhân tỷ giá ngoại tệ: 1 USD = 25.400 VND. Số lượng 2 cái giá 100.00 USD/cái -> Chuẩn hóa thành 2 cái, đơn giá 2.540.000,00 VND/cái.
* **Input State:**
  * `pr_data`: `target_uom="cái"`, `target_currency="VND"`.
  * `confirmed_quotes`: 1 quote, currency="USD", item: `unit="cái"`, `quantity=Decimal("2")`, `unit_price=Decimal("100.00")`.
* **Expected Output ở Biên:**
  ```python
  artifact = result["normalized_quotes"][0]
  assert artifact.status == NormalizationStatus.NORMALIZED
  item = artifact.items[0]
  assert item.normalized_quantity == Decimal("2")
  assert item.normalized_unit_price == Decimal("2540000.00")  # 100.00 * 25400
  assert item.normalized_currency == "VND"
  assert item.rule_id == "uom:cái->cái;fx:USD->VND"
  ```

---

### TC-04 — Combined Conversion: Kết hợp cả UOM và FX kèm Làm tròn chuẩn 0.01
* **Mục tiêu:** Kiểm tra kết hợp đồng thời đổi đơn vị và đổi tiền tệ kèm quy tắc làm tròn ROUND_HALF_UP tới 2 chữ số thập phân (`Decimal("0.01")`).
  * Ví dụ: 1 tá = 12 cái. Mua 1 tá giá 50.00 USD -> Đơn vị cái, đơn giá VND:
    * `unit_price = 50.00 / 12 * 25400 = 105833.3333...` -> Làm tròn: `105833.33` VND.
* **Input State:**
  * `pr_data`: `target_uom="cái"`, `target_currency="VND"`.
  * `confirmed_quotes`: item: `unit="tá"`, `quantity=Decimal("1")`, `unit_price=Decimal("50.00")`, quote currency="USD".
* **Expected Output ở Biên:**
  ```python
  item = result["normalized_quotes"][0].items[0]
  assert item.normalized_quantity == Decimal("12")
  assert item.normalized_uom == "cái"
  assert item.normalized_unit_price == Decimal("105833.33")
  assert item.normalized_currency == "VND"
  assert item.rule_id == "uom:tá->cái;fx:tá->cái;fx:USD->VND" or "uom:tá->cái;fx:USD->VND"
  ```

---

### TC-05 — Missing UOM Mapping: Khác loại đơn vị đo lường (Incompatible Units)
* **Mục tiêu:** PR yêu cầu `"cái"` (đơn vị đếm), nhưng báo giá là `"kg"` (đơn vị khối lượng) hoặc đơn vị lạ `"pallet"`. Không thể tự quy đổi -> Sinh issue, status `NEEDS_MAPPING`, toàn bộ normalized fields là `None`.
* **Input State:**
  * `pr_data`: `target_uom="cái"`, `target_currency="VND"`.
  * `confirmed_quotes`: item có `unit="kg"`, `quantity=Decimal("100")`, `unit_price=Decimal("50000.00")`.
* **Expected Output ở Biên:**
  ```python
  artifact = result["normalized_quotes"][0]
  assert artifact.status == NormalizationStatus.NEEDS_MAPPING
  assert len(artifact.issues) == 1
  assert "missing UOM mapping 'kg' -> 'cái'" in artifact.issues[0]

  # Bất biến: Tất cả trường normalized phải là None
  item = artifact.items[0]
  assert item.normalized_quantity is None
  assert item.normalized_uom is None
  assert item.normalized_unit_price is None
  assert item.normalized_currency is None
  assert item.rule_id is None
  # Dữ liệu nguồn vẫn được bảo toàn
  assert item.source_quantity == Decimal("100")
  assert item.source_uom == "kg"
  ```

---

### TC-06 — Missing FX Rate: Tiền tệ chưa được định cấu hình tỷ giá
* **Mục tiêu:** Báo giá sử dụng ngoại tệ lạ (ví dụ `"AUD"` hoặc `"SGD"` không có trong `FX_RATES_TO_VND`). Hệ thống không được tự đoán tỷ giá -> Báo `NEEDS_MAPPING`.
* **Input State:**
  * `pr_data`: `target_currency="VND"`.
  * `confirmed_quotes`: quote currency=`"AUD"`.
* **Expected Output ở Biên:**
  ```python
  artifact = result["normalized_quotes"][0]
  assert artifact.status == NormalizationStatus.NEEDS_MAPPING
  assert any("missing FX rate 'AUD' -> 'VND'" in issue for issue in artifact.issues)
  item = artifact.items[0]
  assert item.normalized_unit_price is None
  assert item.normalized_currency is None
  ```

---

### TC-07 — Mixed Items in One Quote: 1 dòng thành công, 1 dòng lỗi
* **Mục tiêu:** Trong 1 báo giá có 2 dòng: dòng 1 quy đổi thành công (`cái` -> `cái`), dòng 2 thiếu UOM (`mét` -> `cái`). Kết quả: toàn bộ báo giá bị gắn cờ `NEEDS_MAPPING`, dòng 1 vẫn có đủ giá trị normalized, dòng 2 mang giá trị `None`.
* **Input State:**
  * Quote có Item 0 (unit="cái") và Item 1 (unit="mét"). Target UOM = "cái".
* **Expected Output ở Biên:**
  ```python
  artifact = result["normalized_quotes"][0]
  assert artifact.status == NormalizationStatus.NEEDS_MAPPING
  assert len(artifact.items) == 2

  # Dòng 0: Chuẩn hóa thành công
  assert artifact.items[0].normalized_quantity is not None
  assert artifact.items[0].normalized_unit_price is not None

  # Dòng 1: Thất bại, trường normalized là None
  assert artifact.items[1].normalized_quantity is None
  assert artifact.items[1].normalized_unit_price is None
  assert any("items[1]: missing UOM mapping" in issue for issue in artifact.issues)
  ```

---

### TC-08 — Multiple Quotes Normalization: Xử lý đồng thời nhiều báo giá
* **Mục tiêu:** Khi có 2 báo giá từ 2 NCC khác nhau (NCC A dùng USD, NCC B dùng EUR), hàm xử lý độc lập, sinh ra đúng 2 artifact với revision ID riêng biệt và tỷ giá tương ứng.
* **Input State:**
  * `state["confirmed_quotes"]`: [Quote_A (USD), Quote_B (EUR)].
* **Expected Output ở Biên:**
  ```python
  assert len(result["normalized_quotes"]) == 2
  art_a = result["normalized_quotes"][0]
  art_b = result["normalized_quotes"][1]
  assert art_a.quotation_revision_id != art_b.quotation_revision_id
  assert art_a.items[0].normalized_currency == "VND"
  assert art_b.items[0].normalized_currency == "VND"
  assert art_a.items[0].rule_id.endswith("fx:USD->VND")
  assert art_b.items[0].rule_id.endswith("fx:EUR->VND")
  ```

---

### TC-09 — Empty Confirmed Quotes: Danh sách đầu vào rỗng
* **Mục tiêu:** Khi `confirmed_quotes = []` (chưa có báo giá nào được duyệt), hàm trả về danh sách rỗng an toàn, không ném lỗi.
* **Input State:** `state = {"confirmed_quotes": []}`.
* **Expected Output ở Biên:**
  ```python
  result = normalize(state)
  assert result == {"normalized_quotes": []}
  ```

---

## III. Ma trận đánh giá theo 6 nguyên tắc kiểm thử

| Nguyên tắc | Đánh giá bộ test `normalize` |
|:---|:---|
| **1. Assert cụ thể hay không crash?** | Cụ thể 100%: Assert từng con số Decimal tính toán (ví dụ `105833.33`), định dạng `rule_id`, thông báo issue `items[i]: missing...`, status enum `NORMALIZED` vs `NEEDS_MAPPING`. |
| **2. Expected độc lập hay copy logic?** | Độc lập: Con số mong đợi được tính trước bằng tay theo công thức nghiệp vụ (100 USD * 25400 = 2540000; 50 USD / 12 * 25400 = 105833.33), không dùng lại hàm nội bộ. |
| **3. Có mock quá mức không?** | **0% Mock**: Node là hàm thuần túy toán học và tra cứu bảng hằng số, không gọi I/O ngoài, chạy 100% code thật. |
| **4. Test behavior hay implementation?** | Hoàn toàn theo Behavior: State In (`confirmed_quotes`, `pr_data`) ➡️ State Out (`normalized_quotes`). Không test hàm private `_uom_factor`, `_currency_rate`, `_rule_id`. |
| **5. Đổi toán tử / xóa dòng có đỏ không?** | Đỏ ngay lập tức: Đổi chia sang nhân ở đơn giá (`unit_price * uom_factor`) -> TC-02 đỏ; đổi làm tròn sang `ROUND_FLOOR` -> TC-04 đỏ; quên set `NEEDS_MAPPING` khi có issue -> TC-05 đỏ. |
| **6. Đủ edge case thiết yếu không?** | Đủ: Cùng đơn vị (identity), đổi UOM (bội số), đổi FX (tỷ giá), kết hợp UOM+FX kèm làm tròn số lẻ, UOM không tương thích, ngoại tệ lạ, hỗn hợp dòng đúng/sai trong cùng 1 quote, danh sách rỗng. |
