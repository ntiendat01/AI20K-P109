# Spec MVP — AI Agent Xử lý Đề nghị Mua sắm & So sánh NCC

**Dự án P-109 — VinUni AI20K Build Phase, Cohort 4** · Phạm vi: mức **Cơ bản**

---

## 1. Mục tiêu

Xây dựng web app cho phép nhân viên mua sắm tạo Đề nghị mua hàng (PR), upload báo giá từ nhiều nhà cung cấp (NCC), để agent tự động trích xuất – chuẩn hóa – so sánh và đề xuất NCC kèm lý do; Quản lý xem xét và duyệt để tạo Đơn mua hàng (PO). Con người luôn là người quyết định cuối cùng (HITL) — agent **không** tự đặt hàng.

## 2. Vai trò người dùng

| Vai trò               | Quyền hạn                                                             |
| --------------------- | --------------------------------------------------------------------- |
| **Nhân viên mua sắm** | Tạo PR, upload báo giá, xem bảng so sánh & đề xuất, gửi yêu cầu duyệt |
| **Quản lý duyệt**     | Xem PR + bảng so sánh + giải thích của agent, duyệt/từ chối, tạo PO   |

## 3. Luồng nghiệp vụ chính

```javascript
flowchart LR
    A[Nhân viên tạo PR] --> B[Upload báo giá<br/>PDF/email nhiều NCC]
    B --> C[Agent: OCR/Parser<br/>trích xuất số liệu]
    C --> D[Agent: Chuẩn hóa<br/>đơn vị, tiền tệ, hạng mục]
    D --> E[Agent: So sánh NCC<br/>giá - chất lượng - thời gian giao]
    E --> F[Agent đề xuất NCC<br/>kèm lý do]
    F --> G{Quản lý duyệt?}
    G -->|Duyệt| H[Tạo PO]
    G -->|Từ chối| B
```

## 4. Yêu cầu chức năng (MVP)

### 4.1 Đăng nhập & phân quyền

- Đăng nhập theo tài khoản, phân 2 vai trò cố định (mua sắm / quản lý).
- Mỗi vai trò chỉ thấy các chức năng tương ứng (route guard).

### 4.2 Tạo & quản lý PR

- Form nhập PR: mã PR, người tạo, danh mục hàng hóa/dịch vụ cần mua, số lượng, ngân sách dự kiến, hạn giao.
- Danh sách PR theo trạng thái: Nháp / Chờ báo giá / Đang so sánh / Chờ duyệt / Đã duyệt / Từ chối.

### 4.3 Upload & trích xuất báo giá

- Upload file PDF (và tối thiểu 1 định dạng email/txt) báo giá từ nhiều NCC cho cùng một PR.
- Agent dùng OCR/parser bảng (Document AI hoặc Camelot) trích: tên NCC, mã/tên sản phẩm, đơn giá, số lượng, thành tiền, thời gian giao, điều khoản thanh toán.
- Hiển thị lại bản trích xuất để nhân viên xác nhận/sửa tay trước khi đưa vào so sánh (kiểm soát độ chính xác số liệu tài chính).

### 4.4 Chuẩn hóa dữ liệu

- Quy đổi đơn vị, tiền tệ về một chuẩn chung.
- Ánh xạ (matching) các mặt hàng tương đương giữa các báo giá khác nhau về tên gọi.

### 4.5 So sánh & đề xuất NCC

- Bảng so sánh song song các NCC theo 3 tiêu chí: giá, chất lượng (dựa hồ sơ NCC có sẵn trong vector DB), thời gian giao.
- Agent dùng RAG trên chính sách mua sắm nội bộ để kiểm tra điều kiện hợp lệ (vd: NCC có trong danh sách được duyệt không).
- Sinh đề xuất NCC nên chọn kèm đoạn giải thích lý do (căn cứ trên số liệu + chính sách).

### 4.6 Duyệt & tạo PO

- Quản lý xem PR, bảng so sánh, đề xuất và giải thích → chọn Duyệt/Từ chối.
- Khi duyệt: hệ thống sinh PO (mã PO, NCC, hạng mục, tổng giá trị, điều khoản) ở trạng thái nháp để xuất/lưu — **không** tự động gửi/đặt hàng.

## 5. Data model (rút gọn)

| Bảng                | Trường chính                                                                                   |
| ------------------- | ---------------------------------------------------------------------------------------------- |
| `users`             | id, tên, email, vai trò                                                                        |
| `purchase_requests` | id, mã PR, người tạo, danh mục, ngân sách, hạn giao, trạng thái                                |
| `suppliers`         | id, tên, thông tin liên hệ, điểm đánh giá (nếu có)                                             |
| `quotations`        | id, pr\_id, supplier\_id, file gốc, thời gian giao, điều khoản thanh toán, trạng thái xác nhận |
| `quotation_items`   | id, quotation\_id, tên hàng chuẩn hóa, đơn giá, số lượng, thành tiền                           |
| `purchase_orders`   | id, pr\_id, supplier\_id, tổng giá trị, trạng thái, người duyệt, thời gian duyệt               |

## 6. Kiến trúc hệ thống

```javascript
flowchart TB
    FE[React Frontend<br/>bảng so sánh, form PR/PO] --> BE[FastAPI Backend]
    BE --> DB[(PostgreSQL)]
    BE --> AGENT[LangGraph Agent<br/>multi-step pipeline]
    AGENT --> OCR[OCR/Parser<br/>Document AI / Camelot]
    AGENT --> VDB[(Vector DB<br/>hồ sơ NCC + chính sách mua sắm)]
    BE -.deploy.-> RENDER[Render]
```

- **Backend:** FastAPI, expose REST API cho PR/quotation/comparison/PO.
- **Agent:** LangGraph điều phối các bước OCR → chuẩn hóa → so sánh → đề xuất, dạng multi-step, mỗi bước log lại để minh bạch (traceable).
- **Vector DB:** lưu hồ sơ NCC (dùng cho matching sản phẩm & chấm điểm chất lượng) và tài liệu chính sách mua sắm cho RAG.
- **DB quan hệ:** PostgreSQL lưu toàn bộ dữ liệu giao dịch (PR, quotation, PO).
- **Deploy:** Render, tách frontend/backend hoặc container hóa.

## 7. API endpoints tối thiểu

```javascript
POST   /auth/login
GET    /prs                  # danh sách PR theo vai trò
POST   /prs                  # tạo PR
POST   /prs/{id}/quotations  # upload báo giá cho 1 PR
GET    /prs/{id}/comparison  # bảng so sánh NCC + đề xuất của agent
POST   /prs/{id}/approve     # quản lý duyệt/từ chối
POST   /prs/{id}/po          # tạo PO sau khi duyệt
```

## 8. Ràng buộc bắt buộc (đã có trong đề bài — cần thể hiện rõ trong thiết kế)

- **HITL bắt buộc** ở bước chọn NCC và duyệt PO — UI phải có bước xác nhận tường minh, agent chỉ đề xuất.
- **Bảo mật báo giá:** phân quyền theo vai trò, không lộ báo giá của NCC này cho NCC khác; hạn chế truy cập file gốc theo PR.
- **Độ chính xác trích xuất tài chính:** bắt buộc bước nhân viên xác nhận số liệu OCR trước khi dùng để so sánh (mục 4.3).
- **Kiểm soát chi phí xử lý:** giới hạn số trang/số file OCR mỗi lần upload; cache kết quả trích xuất theo file để tránh gọi lại.

## 9. Tiêu chí nghiệm thu MVP (Definition of Done)

- Đăng nhập phân biệt được 2 vai trò, đúng quyền truy cập.
- Tạo được PR và upload ≥2 báo giá (PDF) cho cùng PR.
- Agent trích xuất đúng các trường chính (đơn giá, số lượng, thời gian giao) trên bộ dữ liệu test, có bước xác nhận thủ công.
- Bảng so sánh hiển thị đủ 3 tiêu chí (giá/chất lượng/thời gian giao) và một đề xuất kèm giải thích.
- Quản lý duyệt được và hệ thống sinh ra PO ở trạng thái nháp, không tự gửi đi.
- Toàn bộ luồng chạy được end-to-end trên bản deploy Render (không chỉ local).

## 10. Đề xuất trình tự triển khai

1. Data model + backend CRUD cơ bản (PR, supplier, quotation) + auth 2 vai trò.
2. Upload file + tích hợp OCR/parser, hiển thị bản trích xuất để xác nhận.
3. Bước chuẩn hóa + logic so sánh (rule-based trước, agent/LLM đề xuất sau).
4. Bảng so sánh trên frontend + luồng duyệt → tạo PO.
5. Deploy Render, chạy thử end-to-end với bộ dữ liệu tổng hợp đã có.
