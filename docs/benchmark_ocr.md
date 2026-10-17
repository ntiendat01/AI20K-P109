# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR (TỰ ĐỘNG BATCH EVALUATION)

**Tổng số cặp file đánh giá: 19 tài liệu**
- **Tỉ lệ đúng trung bình tổng quan (Average Accuracy): 87.58%**
- Điểm trung bình thông tin chung (Header Score): 80.05%
- Điểm trung bình chi tiết mặt hàng (Items Score): 91.85% (F1 trung bình: 100.00%)
- Exact match trường số trung bình: 79.19%
- Precision / Recall dòng hàng trung bình: Precision: 100.00%, Recall: 100.00%

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ TRÊN TOÀN TẬP DỮ LIỆU

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế TB | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **79.19%** | ⚠️ CẦN XEM LẠI | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 📊 BẢNG TỔNG HỢP KẾT QUẢ TỪNG TÀI LIỆU

| STT | Tên File OCR | Tên Ground Truth | Tổng quan | Header | Items | Exact Số | Dòng hàng (P / R) | Trạng thái |
| :-: | :--- | :--- | :-: | :-: | :-: | :-: | :-: | :-: |
| 1 | `Bao_Gia_1_Tan_Viet_ocr.json` | `Bao_Gia_1_Tan_Viet.json` | **93.75%** | 87.50% | 100.0% | 85.71% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 2 | `bao_gia_21_ecolife_tea_ocr.json` | `bao_gia_21_ecolife_tea.json` | **81.25%** | 62.50% | 100.0% | 80.00% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 3 | `bao_gia_22_minh_duc_stationery_ocr.json` | `bao_gia_22_minh_duc_stationery.json` | **87.50%** | 75.00% | 100.0% | 92.31% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 4 | `bao_gia_24_hoang_gia_agrifood_ocr.json` | `bao_gia_24_hoang_gia_agrifood.json` | **86.04%** | 74.38% | 96.2% | 89.47% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 5 | `Bao_Gia_2_Green_Dist_ocr.json` | `Bao_Gia_2_Green_Dist.json` | **92.31%** | 84.63% | 100.0% | 85.71% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 6 | `Bao_Gia_3_Tong_Kho_Viet_A_ocr.json` | `Bao_Gia_3_Tong_Kho_Viet_A.json` | **77.45%** | 54.90% | 100.0% | 57.14% | P: 100.00%<br>R: 100.00% | ⚠️ XEM XÉT |
| 7 | `Bao_Gia_4_An_Phat_ocr.json` | `Bao_Gia_4_An_Phat.json` | **85.53%** | 83.06% | 80.0% | 85.71% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 8 | `Bao_Gia_5_Mekong_Star_ocr.json` | `Bao_Gia_5_Mekong_Star.json` | **80.14%** | 60.27% | 100.0% | 57.14% | P: 100.00%<br>R: 100.00% | ⚠️ XEM XÉT |
| 9 | `Bao_Gia_Dau_An_VinaEdible_ocr.json` | `Bao_Gia_Dau_An_VinaEdible.json` | **92.94%** | 85.89% | 100.0% | 85.71% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 10 | `Bao_Gia_Dau_Goi_Moc_Sac_ocr.json` | `Bao_Gia_Dau_Goi_Moc_Sac.json` | **86.83%** | 73.67% | 100.0% | 71.43% | P: 100.00%<br>R: 100.00% | ⚠️ XEM XÉT |
| 11 | `Bao_Gia_Gao_ST25_Dai_Nam_ocr.json` | `Bao_Gia_Gao_ST25_Dai_Nam.json` | **93.12%** | 86.24% | 100.0% | 85.71% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 12 | `Bao_Gia_Hat_Nem_Tam_An_ocr.json` | `Bao_Gia_Hat_Nem_Tam_An.json` | **93.75%** | 87.50% | 100.0% | 85.71% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 13 | `Bao_Gia_Khan_Giay_Pulppy_Silk_ocr.json` | `Bao_Gia_Khan_Giay_Pulppy_Silk.json` | **88.16%** | 85.32% | 85.0% | 85.71% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 14 | `Bao_Gia_London_Botanic_GBP_ocr.json` | `Bao_Gia_London_Botanic_GBP.json` | **91.42%** | 87.50% | 92.2% | 85.71% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 15 | `Bao_Gia_Nen_Thom_Aura_ocr.json` | `Bao_Gia_Nen_Thom_Aura.json` | **93.75%** | 87.50% | 100.0% | 85.71% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 16 | `Bao_Gia_Nuoc_Khoang_Vitalis_ocr.json` | `Bao_Gia_Nuoc_Khoang_Vitalis.json` | **81.38%** | 86.76% | 60.0% | 57.14% | P: 100.00%<br>R: 100.00% | ⚠️ XEM XÉT |
| 17 | `Bao_Gia_Nuoc_Lau_San_A_Chau_ocr.json` | `Bao_Gia_Nuoc_Lau_San_A_Chau.json` | **93.75%** | 87.50% | 100.0% | 85.71% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 18 | `Bao_Gia_Nuoc_Rua_Chen_EcoLife_ocr.json` | `Bao_Gia_Nuoc_Rua_Chen_EcoLife.json` | **87.71%** | 84.43% | 85.0% | 85.71% | P: 100.00%<br>R: 100.00% | ✅ ĐẠT |
| 19 | `Bao_Gia_Sua_Ba_Vi_ocr.json` | `Bao_Gia_Sua_Ba_Vi.json` | **77.24%** | 86.48% | 46.7% | 57.14% | P: 100.00%<br>R: 100.00% | ⚠️ XEM XÉT |

---

## 📑 CHI TIẾT ĐÁNH GIÁ TỪNG TÀI LIỆU

### Tài liệu 1: `Bao_Gia_1_Tan_Viet_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_1_Tan_Viet.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 93.75%**
- Điểm thông tin chung (Header Score): 87.50%
- Điểm chi tiết mặt hàng (Items Score): 100.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **85.71%** (6/7 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY CP TẬP ĐOÀN HÓA MỸ PHẨM TÂN VIỆT | Công ty CP Tập đoàn Hóa Mỹ Phẩm Tân Việt | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 24 | 24 | ✅ | **100.0%** |
| `lead_time_days` | 2 | 24–48 giờ | ✅ | **100.0%** |
| `payment_terms` | Tạm ứng 30% khi ký hợp đồng, 70% còn lại trong vòng 15 ngày kể từ ngày giao nhận và nhận đủ hóa đơn GTGT. | Tạm ứng 30% khi ký hợp đồng, 70% còn lại trong vòng 15 ngày kể từ ngày giao nhận và nhận đủ hóa đơn GTGT. | ✅ | **100.0%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Nước giặt xả sinh học Tân Việt Eco (Can 3.8kg)<br>OCR: Nước giặt xả sinh học Tân Việt Eco (Can 3.8kg) | ✅ | ✅ | ✅ | ✅ | **100.0%** |

---

### Tài liệu 2: `bao_gia_21_ecolife_tea_ocr.json`
- **Ground Truth tương ứng:** `bao_gia_21_ecolife_tea.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 81.25%**
- Điểm thông tin chung (Header Score): 62.50%
- Điểm chi tiết mặt hàng (Items Score): 100.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **80.00%** (8/10 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY CP NƯỚC GIẢI KHÁT & TRÀ THIÊN NHIÊN ECOLIFE | Công ty CP Nước Giải Khát & Trà Thiên Nhiên EcoLife | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | *null* | ❌ | **0.0%** |
| `shipping_fee` | 150000.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | *null* | 12 | ❌ | **0.0%** |
| `lead_time_days` | 2 | 02 ngày làm việc | ✅ | **100.0%** |
| `payment_terms` | Chuyển khoản 100% trong vòng 15 ngày sau khi nhận hàng và hóa đơn GTGT điện tử. | Chuyển khoản 100% trong vòng 15 ngày sau khi nhận hàng và hóa đơn GTGT điện tử. | ✅ | **100.0%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **2**
- Số mặt hàng OCR nhận diện: **2**
- Số mặt hàng khớp: **2** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Trà xanh đóng chai Oolong Tea Plus 450ml (Thùng 24 chai)<br>OCR: Trà xanh đóng chai Oolong Tea Plus 450ml (Thùng 24 chai) | ✅ | ✅ | ✅ | ✅ | **100.0%** |
| 2 | GT: Trà đào hạt chia ít đường Nature Chill 350ml (Lốc 6 chai)<br>OCR: Trà đào hạt chia ít đường Nature Chill 350ml (Lốc 6 chai) | ✅ | ✅ | ✅ | ✅ | **100.0%** |

---

### Tài liệu 3: `bao_gia_22_minh_duc_stationery_ocr.json`
- **Ground Truth tương ứng:** `bao_gia_22_minh_duc_stationery.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 87.50%**
- Điểm thông tin chung (Header Score): 75.00%
- Điểm chi tiết mặt hàng (Items Score): 100.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **92.31%** (12/13 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY TNHH PHÂN PHỐI VĂN PHÒNG PHẨM MINH ĐỨC | Công ty TNHH Phân Phối Văn Phòng Phẩm Minh Đức | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.1 | 0.1 | ✅ | **100.0%** |
| `vat_included` | False | *null* | ❌ | **0.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | *null* | *null* | ✅ | **100.0%** |
| `lead_time_days` | 1 | 01 ngày làm việc | ✅ | **100.0%** |
| `payment_terms` | Thanh toán bằng chuyển khoản trong vòng 07 ngày làm việc kể từ ngày giao hàng. | Thanh toán bằng chuyển khoản trong vòng 07 ngày làm việc kể từ ngày giao hàng. | ✅ | **100.0%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **3**
- Số mặt hàng OCR nhận diện: **3**
- Số mặt hàng khớp: **3** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Giấy in Double A Định lượng 70gsm Khổ A4 (Thùng 5 ram)<br>OCR: Giấy in Double A Định lượng 70gsm Khổ A4 (Thùng 5 ram) | ✅ | ✅ | ✅ | ✅ | **100.0%** |
| 2 | GT: Bút bi bấm Thiên Long 0.5mm Mực xanh (Hộp 20 cây)<br>OCR: Bút bi bấm Thiên Long 0.5mm Mực xanh (Hộp 20 cây) | ✅ | ✅ | ✅ | ✅ | **100.0%** |
| 3 | GT: Bìa còng bật KingJim 7cm Khổ F4<br>OCR: Bìa còng bật KingJim 7cm Khổ F4 | ✅ | ✅ | ✅ | ✅ | **100.0%** |

---

### Tài liệu 4: `bao_gia_24_hoang_gia_agrifood_ocr.json`
- **Ground Truth tương ứng:** `bao_gia_24_hoang_gia_agrifood.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 86.04%**
- Điểm thông tin chung (Header Score): 74.38%
- Điểm chi tiết mặt hàng (Items Score): 96.18% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **89.47%** (17/19 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY CỔ PHẦN CHẾ BIẾN NÔNG SẢN XUẤT KHẨU HOÀNG GIA | Công ty CP Chế Biến Nông Sản Xuất Khẩu Hoàng Gia | ✅ | **95.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.05 | 0.05 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 300000.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 12 | 12 | ✅ | **100.0%** |
| `lead_time_days` | 4 | 2 - 4 ngày | ❌ | **0.0%** |
| `payment_terms` | Đặt cọc 40% khi ký xác nhận, 60% còn lại thanh toán ngay khi bàn giao đủ hàng. | Đặt cọc 40% khi ký xác nhận, 60% còn lại thanh toán ngay khi bàn giao đủ hàng. | ✅ | **100.0%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **5**
- Số mặt hàng OCR nhận diện: **5**
- Số mặt hàng khớp: **5** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **80.9%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Hạt điều rang muối vỏ lụa Bình Phước hũ 500g<br>OCR: Hạt điều rang muối vỏ lụa Bình Phước hũ 500g - Hạt loại | ✅ | ✅ | ✅ | ✅ | **97.8%** |
| 2 | GT: Hạt sen sấy giòn nguyên vị lon thiếc 200g<br>OCR: Hạt sen sấy giòn nguyên vị lon thiếc 200g - Sen Huế xịn | ✅ | ✅ | ✅ | ✅ | **97.1%** |
| 3 | GT: Nho khô Ninh Thuận sấy dẻo túi zip 250g<br>OCR: Nho khô Ninh Thuận sấy dẻo túi zip 250g - Không tẩm đường | ✅ | ✅ | ✅ | ✅ | **96.2%** |
| 4 | GT: Chuối sấy giòn xuất khẩu thùng 5kg<br>OCR: Chuối sấy giòn xuất khẩu thùng 5kg - Chuối tiêu organic | ✅ | ✅ | ✅ | ✅ | **95.3%** |
| 5 | GT: Xoài sấy dẻo không đường gói 200g<br>OCR: Xoài sấy dẻo không đường gói 200g - Xoài cát Chu thơm ngọt | ✅ | ✅ | ✅ | ✅ | **94.5%** |

---

### Tài liệu 5: `Bao_Gia_2_Green_Dist_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_2_Green_Dist.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 92.31%**
- Điểm thông tin chung (Header Score): 84.63%
- Điểm chi tiết mặt hàng (Items Score): 100.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **85.71%** (6/7 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY TNHH PHÂN PHỐI QUỐC TẾ XANH | Công ty TNHH Phân Phối Quốc Tế Xanh | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 36 | 36 | ✅ | **100.0%** |
| `lead_time_days` | 2 | 24h tại TP.HCM và 48h tại các tỉnh Đông Nam Bộ | ✅ | **100.0%** |
| `payment_terms` | Thanh toán 50% khi nhận hàng đầy đủ, 50% còn lại trong vòng 30 ngày (Chính sách công nợ tháng cho đối tác). | Thanh toán 50% khi nhận hàng đầy đủ, 50% còn lại trong vòng 30 ngày | ❌ | **77.0%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Nước giặt xả hữu cơ GreenCare Can 3.8kg<br>OCR: Nước giặt xả hữu cơ GreenCare Can 3.8kg | ✅ | ✅ | ✅ | ✅ | **100.0%** |

---

### Tài liệu 6: `Bao_Gia_3_Tong_Kho_Viet_A_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_3_Tong_Kho_Viet_A.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 77.45%**
- Điểm thông tin chung (Header Score): 54.90%
- Điểm chi tiết mặt hàng (Items Score): 100.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **57.14%** (4/7 trường) | ⚠️ CẦN XEM LẠI | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY CP THƯƠNG MẠI & TỔNG KHO VIỆT Á | Công ty CP Thương Mại & Tổng Kho Việt Á | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 36 | *null* | ❌ | **0.0%** |
| `lead_time_days` | 1 | *null* | ❌ | **0.0%** |
| `payment_terms` | Thanh toán 100% chuyển khoản trước khi xuất kho hoặc thanh toán ngay khi lái xe giao hàng đến địa điểm của bên Mua. | Thanh toán 100% chuyển khoản | ❌ | **39.2%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Nước giặt xả sinh học SuperClean Can 3.8kg<br>OCR: Nước giặt xả sinh học SuperClean Can 3.8kg | ✅ | ✅ | ✅ | ✅ | **100.0%** |

---

### Tài liệu 7: `Bao_Gia_4_An_Phat_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_4_An_Phat.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 85.53%**
- Điểm thông tin chung (Header Score): 83.06%
- Điểm chi tiết mặt hàng (Items Score): 80.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **85.71%** (6/7 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY CP SX & XUẤT NHẬP KHẨU AN PHÁT | CÔNG TY CP XNK AN PHÁT | ❌ | **73.3%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | *null* | *null* | ✅ | **100.0%** |
| `lead_time_days` | 2 | 2 ngày | ✅ | **100.0%** |
| `payment_terms` | Tạm ứng 40% giá trị khi ký đơn hàng, 60% thanh toán trong vòng 20 ngày sau khi nhận hàng và hóa đơn GTGT. | Tạm ứng 40% giá trị khi ký đơn hàng, 60% thanh toán trong vòng 20 ngày sau khi nhận hàng | ✅ | **91.2%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **0.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Nước giặt xả AnPhat EcoPro Can 3.8kg<br>OCR: Nước giặt xả AnPhat EcoPro Can 3.8kg | ✅ | ❌ | ✅ | ✅ | **80.0%** |

---

### Tài liệu 8: `Bao_Gia_5_Mekong_Star_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_5_Mekong_Star.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 80.14%**
- Điểm thông tin chung (Header Score): 60.27%
- Điểm chi tiết mặt hàng (Items Score): 100.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **57.14%** (4/7 trường) | ⚠️ CẦN XEM LẠI | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY TNHH HÓA PHẨM MEKONG STAR | Công ty TNHH Hóa Phẩm Mekong Star | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 6 | *null* | ❌ | **0.0%** |
| `lead_time_days` | 2 | *null* | ❌ | **0.0%** |
| `payment_terms` | Thanh toán 50% khi nhận hàng và kiểm tra nguyên đai nguyên kiện, 50% còn lại trong vòng 15 ngày chuyển khoản. | Thanh toán 50% khi nhận hàng và 50% còn lại trong vòng 15 ngày chuyển khoản. | ❌ | **82.2%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Nước giặt đậm đặc Mekong Extra Can 3.8kg<br>OCR: Nước giặt đậm đặc Mekong Extra Can 3.8kg | ✅ | ✅ | ✅ | ✅ | **100.0%** |

---

### Tài liệu 9: `Bao_Gia_Dau_An_VinaEdible_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_Dau_An_VinaEdible.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 92.94%**
- Điểm thông tin chung (Header Score): 85.89%
- Điểm chi tiết mặt hàng (Items Score): 100.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **85.71%** (6/7 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY CP DẦU THỰC VẬT MIỀN NAM (VINAEDIBLE) | Công ty CP Dầu Thực Vật Miền Nam (VinaEdible) | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 24 | 24 | ✅ | **100.0%** |
| `lead_time_days` | 2 | 02 ngày làm việc | ✅ | **100.0%** |
| `payment_terms` | Tạm ứng 30% khi đặt hàng, 70% còn lại thanh toán chuyển khoản trong vòng 15 ngày sau khi giao nhận và xuất hóa đơn VAT điện tử. | Tạm ứng 30% khi đặt hàng, 70% còn lại thanh toán chuyển khoản trong vòng 15 ngày sau khi giao nhận | ✅ | **87.1%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Dầu hướng dương tinh luyện SunGold Can 5L<br>OCR: Dầu hướng dương tinh luyện SunGold Can 5L | ✅ | ✅ | ✅ | ✅ | **100.0%** |

---

### Tài liệu 10: `Bao_Gia_Dau_Goi_Moc_Sac_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_Dau_Goi_Moc_Sac.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 86.83%**
- Điểm thông tin chung (Header Score): 73.67%
- Điểm chi tiết mặt hàng (Items Score): 100.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **71.43%** (5/7 trường) | ⚠️ CẦN XEM LẠI | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY TNHH MỸ PHẨM THIÊN NHIÊN MỘC SẮC | Công ty TNHH Mỹ Phẩm Thiên Nhiên Mộc Sắc | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.1 | 0.1 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 36 | 36 | ✅ | **100.0%** |
| `lead_time_days` | 2 | 1 - 2 ngày làm việc nội thành, 3 ngày với các tỉnh lân cận. | ❌ | **0.0%** |
| `payment_terms` | Đặt cọc 40% giá trị hợp đồng, 60% thanh toán trong vòng 20 ngày sau khi nhận hàng đầy đủ kèm hóa đơn điện tử. | Đặt cọc 40% giá trị hợp đồng, 60% thanh toán trong vòng 20 ngày sau khi nhận hàng đầy đủ | ✅ | **89.3%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Dầu gội thảo dược Bồ Kết & Hà Thủ Ô Mộc Sắc 500ml<br>OCR: Dầu gội thảo dược Bồ Kết & Hà Thủ Ô Mộc Sắc 500ml | ✅ | ✅ | ✅ | ✅ | **100.0%** |

---

### Tài liệu 11: `Bao_Gia_Gao_ST25_Dai_Nam_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_Gao_ST25_Dai_Nam.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 93.12%**
- Điểm thông tin chung (Header Score): 86.24%
- Điểm chi tiết mặt hàng (Items Score): 100.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **85.71%** (6/7 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY CỔ PHẦN NÔNG SẢN ĐẠI NAM (DAI NAM AGRI) | Công ty CP Nông Sản Đại Nam (Đại Nam Agri) | ✅ | **89.9%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.05 | 0.05 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 12 | 12 | ✅ | **100.0%** |
| `lead_time_days` | 3 | 03 ngày làm việc | ✅ | **100.0%** |
| `payment_terms` | Thanh toán 50% ngay sau khi ký đơn đặt hàng, 50% còn lại trong vòng 10 ngày kể từ ngày giao đủ hàng và hóa đơn GTGT. | Thanh toán 50% ngay sau khi ký đơn đặt hàng, 50% còn lại trong vòng 10 ngày kể từ ngày giao đủ hàng và hóa đơn GTGT. | ✅ | **100.0%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Gạo thơm thượng hạng ST25 Ông Cua (Bao 5kg)<br>OCR: Gạo thơm thượng hạng ST25 Ông Cua (Bao 5kg) | ✅ | ✅ | ✅ | ✅ | **100.0%** |

---

### Tài liệu 12: `Bao_Gia_Hat_Nem_Tam_An_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_Hat_Nem_Tam_An.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 93.75%**
- Điểm thông tin chung (Header Score): 87.50%
- Điểm chi tiết mặt hàng (Items Score): 100.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **85.71%** (6/7 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY TNHH THỰC PHẨM SẠCH TÂM AN | Công ty TNHH Thực Phẩm Sạch Tâm An | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 200000.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 18 | 18 | ✅ | **100.0%** |
| `lead_time_days` | 3 | 03 ngày làm việc | ✅ | **100.0%** |
| `payment_terms` | Tạm ứng 30% khi đặt hàng, 70% còn lại thanh toán chuyển khoản trong 15 ngày sau khi nghiệm thu và nhận hóa đơn VAT. | Tạm ứng 30% khi đặt hàng, 70% còn lại thanh toán chuyển khoản trong 15 ngày sau khi nghiệm thu và nhận hóa đơn VAT. | ✅ | **100.0%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Hạt nêm nấm hương rau củ hữu cơ Tâm An 450g<br>OCR: Hạt nêm nấm hương rau củ hữu cơ Tâm An 450g | ✅ | ✅ | ✅ | ✅ | **100.0%** |

---

### Tài liệu 13: `Bao_Gia_Khan_Giay_Pulppy_Silk_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_Khan_Giay_Pulppy_Silk.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 88.16%**
- Điểm thông tin chung (Header Score): 85.32%
- Điểm chi tiết mặt hàng (Items Score): 85.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **85.71%** (6/7 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY TNHH GIẤY TIÊU DÙNG PULPPY SILK VIỆT NAM | Công ty TNHH Giấy Tiêu Dùng Pulppy Silk Việt Nam | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 60 | 60 | ✅ | **100.0%** |
| `lead_time_days` | 2 | 02 ngày làm việc | ✅ | **100.0%** |
| `payment_terms` | Tạm ứng 30% khi ký hợp đồng, 70% còn lại thanh toán chuyển khoản trong 30 ngày đối với khách hàng doanh nghiệp. | Tạm ứng 30% khi ký hợp đồng, 70% còn lại thanh toán chuyển khoản trong 30 ngày | ❌ | **82.5%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **25.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Khăn giấy rút lụa Pulppy Silk Premium 3 lớp (Gói 130 tờ)<br>OCR: Khăn giấy rút lụa Pulppy Silk Premium 3 lớp (Gói 130 tờ) | ✅ | ❌ | ✅ | ✅ | **85.0%** |

---

### Tài liệu 14: `Bao_Gia_London_Botanic_GBP_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_London_Botanic_GBP.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 91.42%**
- Điểm thông tin chung (Header Score): 87.50%
- Điểm chi tiết mặt hàng (Items Score): 92.24% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **85.71%** (6/7 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | LONDON BOTANIC LABORATORIES LTD. | London Botanic Laboratories Ltd. | ✅ | **100.0%** |
| `currency` | GBP | GBP | ✅ | **100.0%** |
| `vat_rate` | 0.2 | 0.2 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 45.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 30 | 30 | ✅ | **100.0%** |
| `lead_time_days` | 3 | 3 business days | ✅ | **100.0%** |
| `payment_terms` | Net 30 days from date of delivery by direct BACS / CHAPS transfer. | Net 30 days from date of delivery by direct BACS / CHAPS transfer. | ✅ | **100.0%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **61.2%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Hyaluronic Acid Intensive Moisture Serum 50ml<br>OCR: Hyaluronic Acid Intensive Moisture Serum 50ml - Triple molecular weight Hyaluronic Acid with 01 bottle | ✅ | ✅ | ✅ | ✅ | **92.2%** |

---

### Tài liệu 15: `Bao_Gia_Nen_Thom_Aura_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_Nen_Thom_Aura.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 93.75%**
- Điểm thông tin chung (Header Score): 87.50%
- Điểm chi tiết mặt hàng (Items Score): 100.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **85.71%** (6/7 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY TNHH AURA HOME DECOR VIỆT NAM | Công ty TNHH Aura Home Decor Việt Nam | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.1 | 0.1 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 150000.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 24 | 24 | ✅ | **100.0%** |
| `lead_time_days` | 4 | 04 ngày | ✅ | **100.0%** |
| `payment_terms` | Tạm ứng 50% khi đặt hàng, 50% còn lại thanh toán ngay khi bàn giao nghiệm thu hàng hóa. | Tạm ứng 50% khi đặt hàng, 50% còn lại thanh toán ngay khi bàn giao nghiệm thu hàng hóa. | ✅ | **100.0%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Nến thơm tinh dầu sáp đậu nành Aura Relaxing Hộp 200g<br>OCR: Nến thơm tinh dầu sáp đậu nành Aura Relaxing Hộp 200g | ✅ | ✅ | ✅ | ✅ | **100.0%** |

---

### Tài liệu 16: `Bao_Gia_Nuoc_Khoang_Vitalis_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_Nuoc_Khoang_Vitalis.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 81.38%**
- Điểm thông tin chung (Header Score): 86.76%
- Điểm chi tiết mặt hàng (Items Score): 60.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **57.14%** (4/7 trường) | ⚠️ CẦN XEM LẠI | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY CP NƯỚC KHOÁNG THIÊN NHIÊN VITALIS | Công ty CP Nước Khoáng Thiên Nhiên Vitalis | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | *null* | *null* | ✅ | **100.0%** |
| `lead_time_days` | 1 | 1 ngày làm việc sau khi gọi nước | ✅ | **100.0%** |
| `payment_terms` | Chuyển khoản định kỳ vào ngày 25 hàng tháng theo số lượng nghiệm thu thực tế trên phiếu giao nhận. | Chuyển khoản định kỳ vào ngày 25 hàng tháng theo số lượng nghiệm thu thực tế trên phiếu | ✅ | **94.0%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **0.0%** |
| `unit` | **100.0%** |
| `unit_price` | **0.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Nước khoáng kiềm thiên nhiên Vitalis Alkaline 19L (Bình có vòi)<br>OCR: Nước khoáng kiềm thiên nhiên Vitalis Alkaline 19L (Bình có vòi) | ❌ | ✅ | ❌ | ✅ | **60.0%** |

---

### Tài liệu 17: `Bao_Gia_Nuoc_Lau_San_A_Chau_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_Nuoc_Lau_San_A_Chau.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 93.75%**
- Điểm thông tin chung (Header Score): 87.50%
- Điểm chi tiết mặt hàng (Items Score): 100.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **85.71%** (6/7 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY TNHH HÓA MỸ PHẨM QUỐC TẾ Á CHÂU | Công ty TNHH Hóa Mỹ Phẩm Quốc Tế Á Châu | ✅ | **100.0%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 36 | 36 | ✅ | **100.0%** |
| `lead_time_days` | 2 | 02 ngày làm việc | ✅ | **100.0%** |
| `payment_terms` | Tạm ứng 30% khi ký hợp đồng, 70% còn lại thanh toán chuyển khoản trong 15 ngày sau khi nhận hàng và hóa đơn GTGT. | Tạm ứng 30% khi ký hợp đồng, 70% còn lại thanh toán chuyển khoản trong 15 ngày sau khi nhận hàng và hóa đơn GTGT. | ✅ | **100.0%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **100.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Nước lau sàn đậm đặc Á Châu Shine Can 3.8kg - Tinh Dầu Sả Chanh<br>OCR: Nước lau sàn đậm đặc Á Châu Shine Can 3.8kg - Tinh Dầu Sả Chanh | ✅ | ✅ | ✅ | ✅ | **100.0%** |

---

### Tài liệu 18: `Bao_Gia_Nuoc_Rua_Chen_EcoLife_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_Nuoc_Rua_Chen_EcoLife.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 87.71%**
- Điểm thông tin chung (Header Score): 84.43%
- Điểm chi tiết mặt hàng (Items Score): 85.00% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **85.71%** (6/7 trường) | ✅ ĐẠT | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY CỔ PHẦN CÔNG NGHỆ SINH HỌC ECOLIFE VIỆT NAM | Công ty CP Công Nghệ Sinh Học EcoLife Việt Nam | ✅ | **94.8%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 0.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 24 | 24 | ✅ | **100.0%** |
| `lead_time_days` | 2 | 02 ngày làm việc | ✅ | **100.0%** |
| `payment_terms` | Tạm ứng 30% khi ký hợp đồng, 70% còn lại thanh toán chuyển khoản trong vòng 20 ngày sau khi bàn giao hàng và gửi hóa đơn điện tử. | Tạm ứng 30% khi ký hợp đồng, 70% còn lại thanh toán chuyển khoản trong vòng 20 ngày sau | ❌ | **80.6%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **100.0%** |
| `unit` | **25.0%** |
| `unit_price` | **100.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Nước rửa chén sinh học EcoClean Can 4.0kg - Hương Quế<br>OCR: Nước rửa chén sinh học EcoClean Can 4.0kg - Hương Quế | ✅ | ❌ | ✅ | ✅ | **85.0%** |

---

### Tài liệu 19: `Bao_Gia_Sua_Ba_Vi_ocr.json`
- **Ground Truth tương ứng:** `Bao_Gia_Sua_Ba_Vi.json`

# BÁO CÁO ĐÁNH GIÁ ĐỘ CHÍNH XÁC OCR

**Tỉ lệ đúng tổng quan (Overall Accuracy): 77.24%**
- Điểm thông tin chung (Header Score): 86.48%
- Điểm chi tiết mặt hàng (Items Score): 46.67% (F1: 100.00%)

## 🏆 BẢNG KIỂM ĐỊNH TUÂN THỦ 2 QUY TẮC NGHIỆP VỤ

| Tiêu chí | Mô tả tiêu chuẩn | Mục tiêu | Kết quả thực tế | Trạng thái | Đánh giá nghiệp vụ |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Exact match trường số** | Khớp tuyệt đối từng trường số với nhãn | ≥ [80]% | **57.14%** (4/7 trường) | ⚠️ CẦN XEM LẠI | Khớp chính xác giá, số lượng, thuế và thời hạn giao hàng |
| **Precision / Recall dòng hàng** | So với golden dataset | P ≥ 90%, R ≥ 85% | **P: 100.00%**<br>**R: 100.00%** | ✅ ĐẠT | Precision cao để tránh sai TCO; Recall để Buyer bổ sung ở HITL-1 |

## 1. Chi tiết từng mục thông tin chung (Header Fields)

| Mục (Field) | Giá trị Ground Truth | Giá trị OCR | Khớp | Tỉ lệ đúng |
| :--- | :--- | :--- | :---: | :---: |
| `supplier_name` | CÔNG TY CỔ PHẦN SỮA QUỐC TẾ BA VÌ | Công ty CP Sữa Quốc Tế Ba Vì | ✅ | **91.8%** |
| `currency` | VND | VND | ✅ | **100.0%** |
| `vat_rate` | 0.08 | 0.08 | ✅ | **100.0%** |
| `vat_included` | False | false | ✅ | **100.0%** |
| `shipping_fee` | 350000.0 | *null* | ❌ | **0.0%** |
| `warranty_months` | 6 | 6 | ✅ | **100.0%** |
| `lead_time_days` | 2 | 2 ngày làm việc | ✅ | **100.0%** |
| `payment_terms` | Thanh toán 100% chuyển khoản trong vòng 10 ngày sau khi nghiệm thu hàng hóa và nhận hóa đơn VAT điện tử. | Thanh toán 100% chuyển khoản trong vòng 10 ngày sau khi nghiệm thu hàng hóa và nhận hóa đơn VAT điện tử. | ✅ | **100.0%** |

## 2. Chi tiết từng mục danh sách mặt hàng (Items Evaluation)

- Số mặt hàng Ground Truth: **1**
- Số mặt hàng OCR nhận diện: **1**
- Số mặt hàng khớp: **1** (Precision: 100.0%, Recall: 100.0%)

### Độ chính xác theo từng thuộc tính của mặt hàng:

| Thuộc tính (Attribute) | Tỉ lệ đúng trung bình |
| :--- | :---: |
| `item_name` | **100.0%** |
| `quantity` | **0.0%** |
| `unit` | **33.3%** |
| `unit_price` | **0.0%** |
| `total_price` | **100.0%** |

### Chi tiết từng dòng mặt hàng:

| # | Tên sản phẩm | Số lượng | Đơn vị | Đơn giá | Thành tiền | Điểm dòng |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| 1 | GT: Sữa tươi tiệt trùng Ba Vì Pure Milk 100% không đường 1L<br>OCR: Sữa tươi tiệt trùng Ba Vì Pure Milk 100% không đường 1L | ❌ | ❌ | ❌ | ✅ | **46.7%** |

---
