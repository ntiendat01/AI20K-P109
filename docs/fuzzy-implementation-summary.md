# Tổng kết triển khai Backend: Fuzzy Matching (Heuristic + Trigram)

Tài liệu này tóm tắt toàn bộ các hạng mục đã được phát triển ở Backend cho luồng **Fuzzy Matching**, đồng thời cung cấp hướng dẫn và hợp đồng giao tiếp (API Contract) cho đội ngũ Frontend để triển khai các bước tiếp theo.

## 1. Các thành phần Backend đã hoàn thiện

### 1.1 Core Logic & Models (Phương án 3)
- **Tệp tin**: `src/models/fuzzy_match.py`, `src/services/fuzzy_match.py`
- **Mô tả**: Áp dụng **Phương án 3 (Heuristic + Trigram)** để so khớp sản phẩm từ báo giá với sản phẩm trong yêu cầu mua sắm (PR) mà **không cần sử dụng LLM**.
- **Quy trình chuẩn hoá (Normalization)**: Xử lý chữ thường, loại bỏ dấu tiếng Việt, loại bỏ từ khoá rác (stop-words), xoá ký tự đặc biệt và áp dụng từ điển đồng nghĩa theo **ranh giới từ/cụm từ**. Vì vậy các alias ngắn như `ss` hoặc `ms` không thể làm hỏng một từ dài hơn.
- **Trọng số tính điểm (Scoring Weights)**:
  - Tên sản phẩm (Name): 60% (Kết hợp 40% Jaro-Winkler + 60% Trigram Dice).
  - Đơn vị tính (UoM): 20% (alias cùng nghĩa đạt 1,0; đơn vị cùng nhóm có thể quy đổi đạt 0,8).
  - Thuộc tính phụ (Attributes): 20%.
- **Thiếu thuộc tính**: Khi một trong hai phía không có thuộc tính phụ, điểm chỉ được chuẩn hoá trên Name và UoM: `(0,60 × Name + 0,20 × UoM) / 0,80`. `attr_score` vẫn trả `0,5` để giữ nguyên API contract.
- **Quy cách kỹ thuật**: Với thép thanh, cặp đường kính và mác thép như `D16 + CB400-V` là định danh kỹ thuật. Hai tên cùng cặp quy cách này được so sánh theo cùng khoá quy cách, dù khác phần mô tả, tiêu chuẩn hoặc nhãn hiệu.
- **Chặn gộp sai theo số hiệu**: Nếu hai tên đều có thông số số nhưng hai tập thông số xung đột (không bên nào là tập con của bên kia), kết quả không được `AUTO_MATCHED`; nó chỉ có thể là `SUGGESTED` để Buyer duyệt.
- **Alias đơn vị hiện có**: `MT/tấn`, `cái/chiếc/ea/pcs` và `ream/ram/rim` được chuẩn hoá về cùng một đơn vị.
- **Ứng viên ghép tay**: Các ứng viên có điểm tên từ `0,55` trở lên được trả về cho UI. Ứng viên dưới ngưỡng đề xuất vẫn có trạng thái `UNMATCHED`, nhưng Buyer có thể chọn chúng trong manual mapping; tên quá khác sẽ không được hiển thị.
- **Quy tắc phân loại**:
  - Tự động gộp (`AUTO_MATCHED`): Confidence >= 90%.
  - Đề xuất gộp (`SUGGESTED`): 70% <= Confidence < 90%.
  - Không khớp (`UNMATCHED`): Confidence < 70%.

### 1.2 Tích hợp LangGraph Pipeline
- **Tệp tin**: `src/agents/nodes/fuzzy_match.py`, `src/agents/graph.py`, `src/agents/state.py`
- **Cập nhật State**: Thêm biến `fuzzy_match_results: dict[str, object]` vào `ProcurementAgentState`.
- **Luồng xử lý**: Node `fuzzy_match` được chèn vào pipeline ngay sau bước chuẩn hoá dữ liệu. Luồng hiện tại: `human_review_extraction` ➔ `normalize` ➔ **`fuzzy_match`** ➔ `check_data_ready`. Node này ghi kết quả batch match vào state.

### 1.3 API Endpoint
- **Tệp tin**: `src/api/routes/__init__.py`
- **Endpoint mới**: `POST /api/quotations/{quotation_id}/items/{item_id}/confirm-match`
- Nhận payload để xác nhận / từ chối hoặc chọn map sản phẩm thủ công (Human-in-the-loop).

### 1.4 Testing & Stability
- Unit test bao phủ normalization, similarity, threshold, alias đơn vị, chặn thông số mâu thuẫn và bộ cặp tên vàng thực tế.
- Sửa lỗi encoding trên Windows (`UTF-8`) ảnh hưởng đến `tests/fixtures/evaluation_cases.py` giúp toàn bộ Unit Test pass xanh.

---

## 2. Lưu ý & Hướng dẫn cho Frontend

Để kết thúc tính năng này, Frontend cần tiếp tục xây dựng UI (dựa trên `ui-coordination-plan.md`) và gọi API đã cung cấp.

### 2.1 Hiển thị trạng thái so khớp (UI/UX)
- Frontend sẽ nhận được dữ liệu match thông qua Graph State hoặc dữ liệu Quote API (`MatchStatus`: `UNMATCHED`, `AUTO_MATCHED`, `SUGGESTED`).
- **Giao diện**:
  - Với item `AUTO_MATCHED`: Hiển thị đã gộp (có thể có badge màu xanh lá "Tự động ghép").
  - Với item `SUGGESTED`: Cần hiển thị UI Component **`FuzzyMatchActionCell`** (như đã quy định) gồm thông tin "Sản phẩm PR gốc", tỷ lệ % trùng khớp (confidence) và 2 action chính: **Confirm (Gộp)** / **Reject (Tách riêng)**.
  - Với item `UNMATCHED`: Cho phép user manual map với PR item thông qua dropdown/modal.

### 2.2 Tích hợp API Contract
Khi người dùng bấm Gộp, Từ chối hoặc tự map thủ công, Frontend gọi Endpoint sau:

**Endpoint**: `POST /api/quotations/{quotation_id}/items/{item_id}/confirm-match`

**Request Payload (`ConfirmMatchRequest`)**:
```json
{
  "pr_item_id": "ID_CUA_PR_ITEM_NEU_CO",
  "action": "CONFIRM" 
}
```
*Các action hợp lệ (enum `MatchAction`)*:
- `CONFIRM`: Xác nhận đề xuất gộp của hệ thống.
- `REJECT`: Từ chối gộp, coi như mặt hàng báo giá không thuộc mặt hàng PR nào.
- `MAP_TO_NEW`: Người dùng tự chọn 1 `pr_item_id` khác (Manual Map).

**Response (Mock MVP)**:
```json
{
  "status": "success",
  "quotation_id": "...",
  "item_id": "...",
  "action": "CONFIRM",
  "mapped_pr_item_id": "...",
  "message": "Đã cập nhật kết quả fuzzy match."
}
```

### 2.3 Công việc tương lai (Future Enhancements)
Hiện tại ở MVP, endpoint `confirm-match` thực hiện việc validate API, nhưng tính năng **tự học (Machine Learning / Synonym Dictionary Persistence)** chưa ghi vào DB thật mà chỉ là logic giả lập in-memory hoặc stub comment.
- Frontend không cần quan tâm chi tiết này, chỉ cần trigger API đầy đủ.
- Việc update State Graph sau user feedback sẽ được hoàn thiện dần ở các phase tiếp theo.
