# User Stories — Procurement Agent

> **Project:** Procurement Agent  
> **Document:** User Stories  
> **Version:** v1.1  
> **Status:** Synchronized with `specs/contracts/`  
> **Last Updated:** 2026-10-05

---

## Epic 1: Procurement Case & Intake

### US-01.1: Tạo Case mua sắm (PR)

**As a** Buyer chuẩn bị so sánh báo giá cho một đợt mua hàng  
**I want to** tạo PR mới với mã PR, danh mục, số lượng cần mua, đơn vị tính chuẩn, đồng tiền mục tiêu, ngân sách dự kiến và hạn giao hàng yêu cầu  
**So that** hệ thống có sẵn tiêu chí chuẩn làm căn cứ so sánh, đối chiếu và quản lý xuyên suốt vòng đời mua sắm.

#### Acceptance Criteria

- **AC1 (Happy):** Given Buyer nhập đủ thông tin hợp lệ (mã PR, số lượng > 0, hạn giao ≥ ngày hiện tại); When bấm "Tạo PR"; Then hệ thống tạo Purchase Request ở trạng thái `awaiting_quotation` (hoặc `draft`) và hiển thị trang nạp báo giá.
- **AC2 (Edge):** Given hạn giao hàng là ngày hôm nay; When bấm "Tạo PR"; Then hệ thống vẫn tạo PR thành công và gắn cờ cảnh báo "Hạn giao trong ngày".
- **AC3 (Negative):** Given thiếu số lượng, số lượng ≤ 0 hoặc hạn giao ở quá khứ; When bấm "Tạo PR"; Then hệ thống từ chối tạo PR và hiển thị lỗi cụ thể tại từng trường vi phạm (HTTP 422).

---

### US-01.2: Tải lên nhiều PDF báo giá

**As a** Buyer đã tạo PR và nhận được báo giá từ các nhà cung cấp  
**I want to** tải cùng lúc 2–10 file PDF báo giá của các NCC vào PR  
**So that** hồ sơ mua sắm được lưu trữ tập trung, cấp mã định danh bất biến và chuẩn bị cho pipeline trích xuất.

#### Acceptance Criteria

- **AC1 (Happy):** Given PR đang ở trạng thái `awaiting_quotation`; When Buyer chọn từ 2 đến 10 file PDF hợp lệ (mỗi file ≤ 2 MB); Then toàn bộ file được lưu bất biến vào `data/uploads/`, hệ thống sinh `document_id`, tính `content_hash` để phục vụ audit/chống trùng lặp, và trả về trạng thái `uploaded` (HTTP 202).
- **AC2 (Edge):** Given PR đã có 10 file; When Buyer cố gắng tải thêm file thứ 11; Then hệ thống từ chối nhận file thứ 11 với thông báo "Tối đa 10 báo giá mỗi PR" và giữ nguyên 10 file hợp lệ đã tải.
- **AC3 (Negative):** Given Buyer chọn 1 file không phải định dạng PDF hoặc vượt quá dung lượng cho phép; When tải lên; Then hệ thống từ chối riêng file lỗi đó, thông báo lý do rõ ràng và vẫn tiếp nhận các file hợp lệ còn lại.

---

### US-01.3: Chặn phân tích khi chưa đủ 2 báo giá từ 2 NCC khác nhau

**As a** Buyer chuẩn bị hồ sơ mua sắm cạnh tranh  
**I want to** bị chặn chuyển sang bước phân tích khi PR chưa có tối thiểu 2 báo giá hợp lệ từ 2 nhà cung cấp khác biệt  
**So that** hồ sơ luôn bảo đảm tính cạnh tranh, minh bạch và tuân thủ chính sách mua sắm nội bộ.

#### Acceptance Criteria

- **AC1 (Happy):** Given PR có tối thiểu 2 báo giá đã xác nhận (`confirmed quotation revisions`) từ 2 nhà cung cấp khác nhau; When Buyer bấm "Bắt đầu phân tích"; Then hệ thống khởi tạo `Analysis` ở trạng thái `queued` và kích hoạt pipeline phân tích.
- **AC2 (Edge - Negative):** Given PR có 2 file báo giá nhưng đều thuộc cùng 1 nhà cung cấp; When bấm "Bắt đầu phân tích"; Then hệ thống chặn phân tích và thông báo "Cần tối thiểu 2 báo giá từ các nhà cung cấp khác nhau để bảo đảm tính cạnh tranh".
- **AC3 (Negative):** Given PR chỉ có 0 hoặc 1 báo giá; When bấm "Bắt đầu phân tích"; Then hệ thống chặn và thông báo "Cần thêm báo giá trước khi bắt đầu so sánh".

---

## Epic 2: Document Processing & HITL Verification

### US-02.1: Trích xuất thông tin NCC và dòng hàng

**As a** Buyer đã nạp báo giá PDF cho PR  
**I want to** hệ thống tự động nhận diện bố cục (layout) và trích xuất tên NCC, mã/tên hàng, số lượng, đơn vị tính và đơn giá của từng dòng hàng  
**So that** tôi không phải nhập liệu thủ công vào bảng tính và giảm thiểu rủi ro sai lệch dữ liệu.

#### Acceptance Criteria

- **AC1 (Happy):** Given file PDF có bảng giá chuẩn gồm nhiều dòng hàng; When hoàn tất quá trình OCR và trích xuất; Then hệ thống sinh bản ghi `QuotationExtraction` (draft) chứa đầy đủ các dòng hàng, gán `confidence_score` cho từng trường và trích xuất `source` (tọa độ bounding box, block ID, số trang).
- **AC2 (Edge):** Given PDF có bảng giá trải dài qua nhiều trang; When trích xuất; Then các dòng hàng được gom nhóm chính xác theo từng block và trang, không bị mất dòng hoặc lặp dòng.
- **AC3 (Negative):** Given PDF scan mờ không thể nhận diện ký tự; When trích xuất; Then hệ thống đánh dấu trạng thái trích xuất lỗi (`failed`), tạo validation issue rõ ràng và cho phép Buyer nhập bổ sung thủ công.

---

### US-02.2a: Trích xuất chi phí phát sinh & điều khoản thanh toán

**As a** Buyer đang đối soát báo giá  
**I want to** hệ thống trích xuất thông tin thuế VAT, trạng thái bao gồm VAT và điều khoản thanh toán  
**So that** tôi có căn cứ tính toán tổng nghĩa vụ tài chính thực tế cho đợt mua hàng.

#### Acceptance Criteria

- **AC1 (Happy):** Given báo giá ghi rõ "VAT 10%" và "Thanh toán trong 30 ngày"; When trích xuất; Then hệ thống nhận diện `vat_rate = 0.10`, `vat_included = false` và `payment_terms = "Thanh toán trong 30 ngày"`.
- **AC2 (Edge):** Given báo giá ghi "Đơn giá đã bao gồm VAT 8%"; When trích xuất; Then hệ thống lưu `vat_rate = 0.08` và đánh dấu `vat_included = true` để không cộng thuế trùng lặp khi tính TCO.
- **AC3 (Contract Note — Phí vận chuyển):** Given báo giá có hoặc không có thông tin phí vận chuyển (shipping cost); When trích xuất; Then hệ thống ghi nhận dạng ghi chú bổ sung, **không bắt buộc đưa vào quotation confirmation contract v1** và tuyệt đối không tự động gán giá trị mặc định là `0` nếu chưa xác nhận được nguồn tính thực tế.

---

### US-02.2b: Trích xuất điều khoản thương mại (bảo hành, lead time)

**As a** Buyer đang đối soát báo giá  
**I want to** hệ thống tự động trích xuất thời hạn bảo hành và thời gian giao hàng (lead time)  
**So that** tôi có đầy đủ dữ liệu phi tài chính để phục vụ so sánh đa tiêu chí.

#### Acceptance Criteria

- **AC1 (Happy):** Given báo giá ghi "Bảo hành 12 tháng, giao hàng trong 7 ngày"; When trích xuất; Then hệ thống lưu `warranty_months = 12` và `lead_time_days = 7`.
- **AC2 (Edge):** Given lead time ghi dạng khoảng thời gian "7–10 ngày làm việc"; When trích xuất; Then hệ thống lưu trữ giá trị diễn giải kèm số ngày trần (10 ngày) để bảo đảm tính an toàn khi phân tích rủi ro.
- **AC3 (Negative):** Given báo giá không đề cập đến thời hạn giao hàng hoặc bảo hành; When trích xuất; Then các trường này để trống (`null`) và được gắn cờ cảnh báo `LOW_CONFIDENCE` hoặc `MISSING_FIELD` để Buyer làm rõ.

---

### US-02.3a: Xem dữ liệu trích xuất song song với PDF gốc (Side-by-side)

**As a** Buyer đang đối soát dữ liệu một báo giá  
**I want to** xem bảng dữ liệu trích xuất đặt cạnh file PDF gốc hiển thị trực quan  
**So that** tôi có thể đối chiếu nhanh từng trường dữ liệu với tài liệu nguồn mà không phải chuyển đổi cửa sổ.

#### Acceptance Criteria

- **AC1 (Happy):** Given báo giá đã hoàn tất trích xuất; When Buyer mở màn hình đối soát; Then bảng dữ liệu và khung xem PDF gốc hiển thị đồng thời song song trên cùng giao diện.
- **AC2 (Edge):** Given Buyer nhấp chuột vào một ô dữ liệu trong bảng trích xuất; When ô được chọn; Then khung xem PDF tự động cuộn đến trang và highlight vùng văn bản nguồn (bounding box/block) của giá trị đó.
- **AC3 (Negative):** Given tài liệu PDF gốc gặp sự cố hiển thị; When mở màn hình đối soát; Then bảng dữ liệu trích xuất vẫn hiển thị đầy đủ kèm thông báo "Không tải được bản xem trước PDF" và nút tải lại.

---

### US-02.3b: Sửa thủ công dữ liệu trích xuất & tạo Confirmed Revision bất biến

**As a** Buyer phát hiện trường trích xuất sai lệch so với PDF gốc  
**I want to** sửa trực tiếp giá trị trên giao diện đối soát và chốt lưu lại thành một phiên bản xác nhận mới (`QuotationRevision`)  
**So that** dữ liệu đưa vào phân tích tuyệt đối chuẩn xác, không ghi đè dữ liệu gốc của OCR và lưu vết kiểm toán đầy đủ.

#### Acceptance Criteria

- **AC1 (Happy):** Given Buyer sửa đơn giá của một dòng hàng; When bấm "Chốt dữ liệu"; Then hệ thống tạo một `QuotationRevision` mới bất biến mang số hiệu `revision_no` tăng dần (ví dụ từ version 1 lên 2), liên kết với `source_item_id` ban đầu và giữ nguyên dữ liệu gốc `QuotationExtraction` để phục vụ audit.
- **AC2 (Concurrency Control):** Given hai Buyer cùng mở đối soát một báo giá; When Buyer A đã chốt trước (tạo revision mới); Then yêu cầu chốt của Buyer B bị từ chối với lỗi xung đột phiên bản (HTTP 409 `REVISION_CONFLICT` qua cơ chế `If-Match: current_version_no`), yêu cầu tải lại dữ liệu mới nhất.
- **AC3 (Negative):** Given Buyer nhập dữ liệu không hợp lệ (nhập chữ vào ô số, số âm); When bấm chốt; Then hệ thống từ chối lưu, hiển thị thông báo lỗi tại ô dữ liệu sai và giữ nguyên giá trị hiện thời.

---

### US-02.4: Bắt buộc đối soát HITL-1 cho mọi báo giá & Cảnh báo trường độ tin cậy thấp

**As a** Buyer chuẩn bị dữ liệu đưa vào phân tích  
**I want to** được hệ thống làm nổi bật các trường có `confidence_score` < 80% (tô đỏ/cảnh báo) và **bắt buộc tôi phải kiểm tra, chốt dữ liệu (Confirm) cho toàn bộ báo giá** bất kể độ tin cậy cao hay thấp  
**So that** không một dữ liệu trích xuất tự động nào của AI có thể lọt vào bước phân tích mà chưa có sự thẩm định và chịu trách nhiệm của con người (bãi bỏ hoàn toàn chế độ auto-confirm hoặc optional review).

#### Acceptance Criteria

- **AC1 (Mandatory HITL-1):** Given báo giá vừa hoàn tất trích xuất; When kết thúc bước validation; Then trạng thái báo giá luôn chuyển sang `needs_confirmation` (job step `waiting_for_human`), yêu cầu Buyer xác nhận trước khi có thể chuyển sang bước chuẩn hóa hoặc phân tích.
- **AC2 (Visual Warning Highlight):** Given trường dữ liệu có độ tin cậy nhỏ hơn ngưỡng toàn cục (`confidence < 0.80`); When hiển thị trên màn hình đối soát; Then trường đó được tô màu cảnh báo nổi bật để Buyer tập trung kiểm tra.
- **AC3 (Low-confidence không chặn chốt):** Given trường có `confidence < 0.80` nhưng Buyer đã nhìn PDF gốc và xác nhận giá trị đó là chính xác; When Buyer bấm "Chốt dữ liệu"; Then hệ thống vẫn cho phép xác nhận thành công (low confidence chỉ cảnh báo thị giác, không tự chặn submit).
- **AC4 (Blocking Severity Issue):** Given báo giá gặp lỗi cấu trúc nghiêm trọng (ví dụ thiếu mã hàng bắt buộc hoặc không thể parse định dạng số); When hiển thị; Then issue được đánh dấu `severity: blocking` và hệ thống chặn nút "Chốt dữ liệu" (HTTP 422) cho đến khi Buyer nhập sửa đầy đủ.

---

## Epic 3: Normalization & Comparison

### US-03.1a: Chuẩn hóa đơn vị tính và tiền tệ

**As a** Buyer so sánh các báo giá sử dụng đơn vị đo lường và đồng tiền khác nhau  
**I want to** hệ thống tự động quy đổi đơn vị tính (UOM) và tiền tệ về hệ quy chuẩn thống nhất của PR dựa trên dữ liệu đã chốt (`confirmed quotation revisions`)  
**So that** các nhà cung cấp được đối chiếu trên cùng một mặt bằng đo lường công bằng và minh bạch.

#### Acceptance Criteria

- **AC1 (Happy):** Given NCC A báo giá theo "hộp" (1 hộp = 10 cái) và NCC B báo giá theo "cái", PR yêu cầu chuẩn "cái"; When chạy chuẩn hóa; Then hệ thống quy đổi đơn giá và số lượng của NCC A về "cái" và lưu vào `NormalizedQuotationArtifact`.
- **AC2 (Deterministic & No Guessing):** Given đơn vị tính hoặc cặp tỷ giá không tồn tại trong bảng quy đổi định sẵn; When chuẩn hóa; Then hệ thống tuyệt đối không tự đoán, đặt giá trị quy chuẩn `normalized_value = null`, gắn cờ `needs_manual_mapping = true` và trạng thái artifact là `needs_mapping` (không fallback về giá trị nguồn).
- **AC3 (Input Invariant):** Given báo giá chưa được Buyer chốt qua HITL-1 (đang ở trạng thái `extracting` hoặc `needs_confirmation`); When chạy chuẩn hóa; Then hệ thống từ chối xử lý và báo lỗi "Chỉ báo giá đã chốt mới được đưa vào chuẩn hóa".

---

### US-03.2: Ma trận so sánh nhà cung cấp

**As a** Buyer đã hoàn tất chốt dữ liệu các báo giá  
**I want to** xem bảng so sánh side-by-side giữa các nhà cung cấp theo các tiêu chí: đơn giá chuẩn hóa, tổng chi phí TCO, lead time, bảo hành và điều khoản thanh toán  
**So that** tôi có cái nhìn tổng quan trực quan để nhận diện thế mạnh và điểm yếu của từng NCC.

#### Acceptance Criteria

- **AC1 (Happy):** Given tối thiểu 2 NCC đã có dữ liệu chốt và tính toán xong TCO; When xem ma trận so sánh; Then hệ thống hiển thị bảng so sánh đa tiêu chí dạng lưới ma trận `SupplierComparisonMatrix` gồm các cell tiêu chí đối đầu rõ ràng.
- **AC2 (Edge - Thiếu mặt hàng):** Given một nhà cung cấp không báo giá cho một dòng hàng nhất định; When hiển thị; Then ô so sánh tương ứng ghi rõ "Không báo giá", không hiển thị số 0 gây hiểu lầm là miễn phí.
- **AC3 (Negative):** Given có báo giá trong đợt so sánh chưa được chốt hoặc snapshot phân tích bị thay đổi; When mở ma trận; Then hệ thống cảnh báo dữ liệu chưa hợp lệ và yêu cầu hoàn tất đối soát trước.

---

### US-03.3: Làm nổi bật chênh lệch vượt ngưỡng

**As a** Buyer đang rà soát ma trận so sánh  
**I want to** hệ thống tự động đánh dấu (highlight) các tiêu chí có giá trị chênh lệch vượt ngưỡng cấu hình (mặc định 15%) so với mức trung bình của các NCC  
**So that** tôi nhanh chóng phát hiện các điểm bất thường, rủi ro đội giá hoặc giá rẻ đột biến cần làm rõ.

#### Acceptance Criteria

- **AC1 (Happy):** Given ngưỡng cấu hình chênh lệch là 15% và đơn giá chuẩn hóa của NCC A cao hơn 20% so với giá trung bình; When hiển thị ma trận; Then ô của NCC A được highlight cảnh báo kèm tỷ lệ chênh lệch (+20%).
- **AC2 (Edge - Bằng ngưỡng):** Given chênh lệch đúng bằng 15%; When hiển thị; Then không đánh dấu highlight (áp dụng quy tắc nghiêm ngặt: chỉ đánh dấu khi mức chênh lệch `>` ngưỡng).
- **AC3 (Negative - Không đủ dữ liệu):** Given chỉ có 1 NCC chào giá cho một dòng hàng cụ thể; When hiển thị; Then ô đó hiển thị nhãn "Không đủ cơ sở so sánh" và không tính toán tỷ lệ chênh lệch trung bình.

---

## Epic 4: Decision Support & Dual-HITL Governance

### US-04.1: Tính tổng chi phí sở hữu (TCO) bằng code xác định

**As a** Buyer đang so sánh các báo giá  
**I want to** xem Tổng chi phí sở hữu (TCO) của từng nhà cung cấp được tính toán bằng công thức logic cố định (deterministic), không để LLM tự tính toán số học  
**So that** con số tài chính tôi và cấp quản lý dựa vào luôn chính xác tuyệt đối, nhất quán và có thể tái lập 100%.

#### Acceptance Criteria

- **AC1 (Happy):** Given đơn giá chuẩn hóa, số lượng, phụ phí và thuế VAT hợp lệ; When tính TCO; Then hệ thống tính toán chính xác theo công thức:  
  $$\text{TCO} = (\text{unit\_price} \times \text{quantity} + \text{surcharges}) \times (1 + \text{vat\_rate})$$  
  và lưu vào artifact `TCOResult`.
- **AC2 (Edge - VAT đã gồm):** Given báo giá ghi nhận `vat_included = true`; When tính TCO; Then hệ thống không cộng thêm thuế VAT lần thứ hai.
- **AC3 (Contract Note — Chi phí vận chuyển):** Given phí vận chuyển chưa có trong contract báo giá; When tính TCO; Then hệ thống không tự động ép `shipping_cost = 0`, ghi rõ trạng thái "Chưa bao gồm phí vận chuyển" để tránh che giấu chi phí tiềm ẩn.

---

### US-04.2a: Cảnh báo chi phí ẩn và điều khoản bất lợi

**As a** Buyer đang đánh giá báo giá  
**I want to** hệ thống tự động rà soát và cảnh báo khi phát hiện các khoản phụ phí ngoài bảng giá chính (chân trang, ghi chú hợp đồng)  
**So that** tôi không chọn nhầm nhà cung cấp có tổng chi phí thực tế bị đội cao sau khi ký hợp đồng.

#### Acceptance Criteria

- **AC1 (Happy):** Given phần ghi chú cuối trang báo giá có ghi "Phí bốc dỡ 1.500.000 VND"; When phân tích rủi ro; Then hệ thống sinh `RiskFlag` cảnh báo chi phí ẩn kèm số tiền và trích dẫn vị trí trong tài liệu gốc.
- **AC2 (Edge):** Given phụ phí đã được khai báo minh bạch trong bảng giá chính và đã tính vào TCO; When phân tích; Then hệ thống không gắn cờ cảnh báo chi phí ẩn trùng lặp.
- **AC3 (Negative):** Given báo giá chứa câu chữ mơ hồ ("Chi phí phát sinh sẽ tính tại thời điểm giao hàng"); When phân tích; Then hệ thống gắn cờ cảnh báo mức độ cao "Điều khoản chi phí không xác định — cần làm rõ với NCC trước khi phê duyệt".

---

### US-04.2b: Cảnh báo lead time vượt hạn giao hàng của PR

**As a** Buyer đã đặt hạn giao hàng yêu cầu cho PR  
**I want to** hệ thống cảnh báo tức thì khi thời gian giao hàng (lead time) của nhà cung cấp vượt quá hạn giao yêu cầu  
**So that** tôi loại trừ hoặc thương lượng lại với các NCC có nguy cơ làm gián đoạn tiến độ hoạt động.

#### Acceptance Criteria

- **AC1 (Happy):** Given hạn giao của PR còn 5 ngày nhưng lead time của NCC là 10 ngày; When phân tích; Then hệ thống gắn cờ rủi ro "Giao hàng trễ hạn 5 ngày so với yêu cầu PR".
- **AC2 (Edge):** Given thời gian giao hàng của NCC bằng đúng số ngày còn lại đến hạn giao; When phân tích; Then hệ thống không cảnh báo vi phạm hạn giao.
- **AC3 (Negative):** Given NCC không ghi rõ lead time trong báo giá; When phân tích; Then hệ thống gắn cờ cảnh báo "Thiếu thông tin thời gian giao hàng — rủi ro tiến độ".

---

### US-04.3a: Đề xuất nhà cung cấp kèm lập luận giải trình minh bạch

**As a** Buyer cần lựa chọn nhà cung cấp tối ưu cho PR  
**I want to** Decision LLM tổng hợp các kết quả tính toán có sẵn (TCO, Comparison, Risk) để đưa ra đề xuất NCC kèm phân tích đánh đổi (trade-offs) và điểm thương lượng  
**So that** tôi có căn cứ lập luận vững chắc, khách quan để trình lên cấp quản lý phê duyệt.

#### Acceptance Criteria

- **AC1 (Happy):** Given các artifact TCO, so sánh và rủi ro đã được tính toán hoàn tất; When Decision LLM tổng hợp đề xuất; Then hệ thống sinh `DecisionProposal` nêu rõ NCC được khuyến nghị, lý do chọn dựa trên số liệu cụ thể và các điểm cần thương lượng thêm.
- **AC2 (Tie-break < 2% TCO):** Given 2 NCC có tổng chi phí TCO chênh lệch dưới 2%; When lập đề xuất; Then hệ thống không ép chọn một bên duy nhất mà trình bày song song cả 2 NCC kèm bảng đánh đổi (Trade-off: giá thấp hơn vs lead time nhanh hơn / bảo hành dài hơn).
- **AC3 (Invariants):** Decision LLM tuyệt đối không tự tính toán lại số học TCO hay tự bịa đặt số liệu mới; mọi con số trong giải trình phải trích xuất chính xác từ các deterministic artifacts có sẵn.

---

### US-04.3b: Xem trích dẫn nguồn của đề xuất (Traceability & Provenance)

**As a** Buyer đang xem xét đề xuất của hệ thống  
**I want to** nhấp vào từng luận điểm, con số trong phần giải trình để xem vị trí trang, đoạn trích và block ID trong tài liệu báo giá gốc  
**So that** tôi có thể kiểm chứng tính xác thực của đề xuất trước khi tin tưởng trình phê duyệt.

#### Acceptance Criteria

- **AC1 (Happy):** Given đề xuất viện dẫn "NCC B có thời gian bảo hành 24 tháng"; When Buyer nhấp vào luận điểm này; Then hệ thống mở bản xem trước PDF và highlight chính xác block văn bản chứa thông tin đó.
- **AC2 (Giá trị do người dùng sửa):** Given luận điểm dựa trên số liệu mà Buyer đã chỉnh sửa tay ở bước đối soát; When xem trích dẫn; Then hệ thống ghi rõ "Dữ liệu do Buyer điều chỉnh tại phiên bản Revision X" kèm giá trị gốc ban đầu.

---

### US-04.4: Buyer thẩm định và trình đề xuất lên Quản lý (HITL-2)

**As a** Buyer đã xem xét toàn bộ đề xuất, ma trận so sánh và các cảnh báo rủi ro của AI  
**I want to** thực hiện bước xác nhận của Buyer (HITL-2) bằng cách chọn `submit` (trình duyệt lên Manager) kèm ghi chú giải trình, hoặc chọn `revise` (yêu cầu điều chỉnh/chạy lại)  
**So that** đề xuất chính thức gửi lên cấp Quản lý luôn có sự cam kết, thẩm định trách nhiệm của Buyer và được đóng gói thành snapshot bất biến.

#### Acceptance Criteria

- **AC1 (Happy — Submit Approval):** Given hồ sơ phân tích đang ở trạng thái `awaiting_buyer_review`; When Buyer chọn hành động `submit` kèm ghi chú giải trình; Then hệ thống lưu bản ghi `BuyerRecommendationConfirmation`, đóng băng snapshot phân tích và chuyển trạng thái analysis sang `pending_manager_approval` (HTTP 200).
- **AC2 (Revise Request):** Given Buyer không đồng tình với đề xuất hoặc cần bổ sung thông tin; When Buyer chọn hành động `revise` kèm lý do bắt buộc; Then hệ thống chuyển trạng thái sang `needs_input` để điều chỉnh mà không gửi lên cấp Quản lý.
- **AC3 (Role Boundary):** Buyer tuyệt đối không có quyền tự phê duyệt cấp quản lý hoặc tự kích hoạt tạo Đơn mua hàng (PO).

---

### US-04.5: Quản lý phê duyệt hồ sơ mua sắm (Approval Governance)

**As a** Procurement Manager có thẩm quyền phê duyệt  
**I want to** xem xét toàn bộ hồ sơ phân tích đã được Buyer thẩm định (`pending_manager_approval`) và ra quyết định `approve`, `revise` hoặc `reject`  
**So that** quy trình mua sắm tuân thủ cơ chế kiểm soát kép (Dual-HITL), đúng ngân sách và chính sách ủy quyền của doanh nghiệp.

#### Acceptance Criteria

- **AC1 (Happy — Approve):** Given hồ sơ ở trạng thái `pending_manager_approval` kèm xác nhận hợp lệ của Buyer; When Manager chọn `approve` và chọn nhà cung cấp trúng thầu (`selected_supplier_id`); Then hệ thống lưu `ApprovalDecision`, đánh dấu hồ sơ là `approved` và tự động kích hoạt tạo Đơn mua hàng nháp (PO draft).
- **AC2 (Revise):** When Manager chọn `revise` kèm lý do bắt buộc; Then hồ sơ được chuyển trả về cho Buyer kèm chỉ đạo điều chỉnh.
- **AC3 (Reject):** When Manager chọn `reject` kèm lý do bắt buộc; Then hồ sơ mua sắm kết thúc với trạng thái `rejected`.
- **AC4 (Precondition Enforcement):** Manager chỉ có thể ra quyết định khi hồ sơ đang ở trạng thái `pending_manager_approval` và snapshot phân tích chưa bị thay thế (`superseded`). Không thể approve nếu thiếu `selected_supplier_id`.

---

### US-04.6: Khởi tạo Đơn mua hàng (PO Issuance) từ quyết định phê duyệt

**As a** Buyer và Manager  
**I want to** hệ thống tự động khởi tạo Đơn mua hàng (Purchase Order) nháp dựa trên quyết định phê duyệt chính thức của Manager và snapshot phân tích bất biến  
**So that** dữ liệu trên PO hoàn toàn khớp đúng với báo giá đã duyệt, loại trừ hoàn toàn sai sót nhập liệu hoặc can thiệp chủ quan.

#### Acceptance Criteria

- **AC1 (Happy):** Given Manager vừa thực hiện quyết định `approve`; When dịch vụ `PurchaseOrderService` xử lý; Then một bản ghi `PurchaseOrder` draft được tạo tự động với mã định danh duy nhất, tham chiếu chính xác đến `approval_decision_id`, `analysis_id`, `supplier_id` và `quotation_revision_id`.
- **AC2 (Idempotency):** Lệnh approve hỗ trợ `Idempotency-Key`; nếu gửi lại yêu cầu cùng key, hệ thống trả về đúng PO đã tạo mà không bao giờ sinh trùng lặp 2 PO cho cùng một quyết định duyệt.
- **AC3 (Data Lineage & Shipping Rule):** Số liệu tài chính trên PO (`subtotal`, `tax_amount`, `total_amount`) được lấy trực tiếp từ `QuotationRevision` và `TCOResult` của nhà cung cấp được duyệt, tuyệt đối không lấy trực tiếp từ text output của LLM. Trường `shipping_amount` lưu giá trị `null` nếu chưa có dữ liệu xác nhận, tuyệt đối không tự gán mặc định bằng `0.00`.

---

## Non-functional Requirements (NFRs)

### 1. Performance (Hiệu suất)
- **Thời gian phản hồi API:** Các thao tác điều hướng, truy vấn dữ liệu cơ bản cần phản hồi dưới 2 giây.
- **Trích xuất dữ liệu:** Quá trình OCR và trích xuất bảng giá từ file PDF thông thường (dưới 10 trang, tối đa 50 dòng hàng) hoàn tất trong tối đa 60 giây.
- **Tính toán & So sánh:** Quá trình chuẩn hóa, tính TCO và dựng ma trận so sánh (tối đa 10 NCC) hoàn thành trong tối đa 10 giây.

### 2. Dual-HITL Governance & Usability
- **HITL-1 (Extraction Confirmation):** Mọi báo giá bắt buộc phải qua bước đối soát và chốt dữ liệu của Buyer trước khi đi vào phân tích. Cảnh báo trực quan rõ ràng các trường nghi ngờ (`confidence < 0.80`).
- **HITL-2 (Buyer Recommendation Review):** Đề xuất của AI bắt buộc phải được Buyer thẩm định và thực hiện hành động `submit` mới có thể chuyển lên cấp Quản lý.
- **Manager Approval:** Quyết định phê duyệt cuối cùng và kích hoạt sinh PO thuộc thẩm quyền độc quyền của Manager.

### 3. Reliability, Immutability & Auditability
- **Tính bất biến (Immutability):** Tài liệu PDF gốc trong `data/uploads/`, kết quả OCR gốc (`QuotationExtraction`), các phiên bản chốt của Buyer (`QuotationRevision`), và các snapshot phân tích (`AnalysisArtifact`) đều mang tính bất biến (immutable), không bị ghi đè.
- **Truy vết nguồn gốc (Provenance):** Mọi con số, nhận định trong báo cáo đề xuất đều liên kết chặt chẽ với block ID, số trang và tọa độ bounding box trong tài liệu gốc.
- **Idempotency & Concurrency:** Các command ghi dữ liệu hỗ trợ `Idempotency-Key` và optimistic concurrency token (`If-Match`), loại bỏ xung đột ghi đè dữ liệu.

### 4. Deterministic Business Rules
- **Tách bạch tính toán tài chính:** TCO, quy đổi đơn vị tính và tỷ giá được xử lý hoàn toàn bằng code logic xác định (deterministic services/tools), không giao phó việc tính toán số học cho mô hình ngôn ngữ lớn (LLM).

---

## Quy tắc quản lý

- Không sửa đổi mã định danh (ID) của User Story khi đã được tham chiếu trong mã nguồn, task hoặc issue tracking.
- Mọi thay đổi về yêu cầu nghiệp vụ phải cập nhật trực tiếp vào tài liệu User Story này để đảm bảo tính đồng bộ với `specs/contracts/`.
- Tiêu chí chấp nhận (Acceptance Criteria) phải kiểm thử được một cách rõ ràng bằng kịch bản hoặc mã kiểm thử tự động.