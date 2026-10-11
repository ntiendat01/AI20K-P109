# Spec: Củng cố bước OCR của luồng upload báo giá chế độ `agent`

Trạng thái: **NHÁP - chờ duyệt** · Người soạn: Claude (planner) · Chưa có TASK_ID
Phạm vi: chỉ đường `extraction_mode=agent` (`TextFirstOCR` → `PaddleOCRHostedClient` → `extract_documents` → LLM).
Ngoài phạm vi: chế độ `parser` (Tesseract, `src/extraction/*`), prompt trích xuất, logic `validate_extraction`/`calculate_tco`/`compare_suppliers`.

## 1. Hiện trạng

Upload PDF ở chế độ `agent` đi qua:

1. `src/api/routes/__init__.py` lưu file, gọi `extract_for_quotation`.
2. `src/services/quotation/intake.py::TextFirstOCR.extract_text`: đọc text layer bằng PyMuPDF; nếu **mọi** trang có chữ thì trả JSON `{pages:[{page_number, raw_text}]}`, ngược lại gọi `PaddleOCRHostedClient` cho **cả file**.
3. `src/services/quotation/ai_extraction.py::PaddleOCRHostedClient.extract_text`: tạo `PaddleOCR(lang="vi", ocr_version="PP-OCRv3", enable_mkldnn=False)` mỗi lần gọi, `client.ocr(path)`, gom `raw_text` theo trang.
4. `src/agents/nodes/extract_documents.py`: gọi OCR rồi LLM; bắt `(HTTPError, OSError, RuntimeError, TimeoutError, ValueError)`, lỗi thì trả draft rỗng.
5. Extractor Groq cắt OCR ở 4500 token (`_fit_context_window`).

## 2. Vấn đề và hướng giải quyết

### V1. Một trang trống làm cả file bị đưa sang Paddle
- Nguyên nhân: điều kiện `all(text.strip() ...)` trong `TextFirstOCR`; trang trắng hoặc chỉ có số trang cũng kích hoạt OCR toàn file. Text layer tốt của các trang khác bị bỏ.
- Hướng giải quyết: quyết định **theo từng trang**. Dùng `src.extraction.detector.has_meaningful_text` (ngưỡng ≥15 ký tự chữ-số). Trang đạt thì lấy text layer; trang không đạt mà có ảnh/hình vẽ thì OCR riêng trang đó (render trang bằng PyMuPDF rồi đưa ảnh cho Paddle); trang không có gì thì ghi `raw_text=""`. Mỗi trang ghi thêm `method: "text" | "ocr" | "blank"`.
- Tiêu chí nghiệm thu: PDF 3 trang gồm 2 trang text + 1 trang trắng → Paddle không được gọi. PDF text + 1 trang scan → Paddle chỉ gọi 1 lần cho trang đó, giữ nguyên text 2 trang còn lại.

### V2. Không giới hạn số trang ở chế độ agent
- Nguyên nhân: chỉ `extract_pdf` (parser) có `MAX_PDF_PAGES = 10`.
- Hướng giải quyết: áp cùng giới hạn trong `TextFirstOCR`; vượt giới hạn → lỗi có mã rõ (xem V5), không OCR.
- **CẦN QUYẾT**: từ chối file hay chỉ xử lý 10 trang đầu kèm cảnh báo? (đề xuất: từ chối, khớp hành vi parser).

### V3. Cấu hình Paddle lệch tài liệu, chưa kiểm chứng API
- Nguyên nhân: code dùng `PP-OCRv3` và `.ocr()` còn `ARCHITECTURE.md`/`AGENT.md` ghi PP-OCRv5; `requirements.txt` ghim `paddleocr>=3.7`. Chưa có bằng chứng chạy thật.
- Hướng giải quyết: bước spike chạy thật trên 2-3 PDF scan mẫu (tiếng Việt) với `paddleocr` đã cài, ghi lại: tham số hợp lệ, `.ocr()` hay `.predict()`, dạng output, có hỗ trợ `lang="vi"` với v5 không, thời gian, RAM. Sau đó đưa `ocr_version` và `lang` thành setting (`paddleocr_version`, `paddleocr_lang`) trong `src/core/config.py`. Chốt phiên bản theo kết quả spike và cập nhật tài liệu cho khớp.
- **CẦN QUYẾT**: nếu v5 không hỗ trợ tiếng Việt tốt, giữ v3 và sửa `ARCHITECTURE.md`, hay đổi engine?
- Dọn: xóa `paddleocr_access_token`/`paddleocr_base_url` và tên "Hosted" nếu không còn dùng (**CẦN DUYỆT** vì đổi `Settings`/`.env.example`).

### V4. Khởi tạo model Paddle mỗi lần gọi
- Nguyên nhân: `PaddleOCR(...)` được tạo trong `extract_text`.
- Hướng giải quyết: tạo engine lười (lazy) một lần cho mỗi process (`functools.lru_cache` hoặc biến module + lock), khóa theo `(lang, version)`. Cho phép tiêm engine giả trong test. Không khởi tạo lúc import để app và test không phải nạp Paddle.
- Tiêu chí: 2 lần OCR liên tiếp chỉ khởi tạo engine 1 lần (test đếm số lần gọi constructor giả).

### V5. Lỗi OCR bị nuốt hoặc gây 500, người dùng không biết nguyên nhân
- Nguyên nhân: `ModuleNotFoundError` và lỗi khác của Paddle không nằm trong danh sách bắt của `extract_documents` nên request sập 500; lỗi nằm trong danh sách thì thành draft rỗng và chỉ hiện cảnh báo chung "AI chưa trích xuất được dòng hàng".
- Hướng giải quyết:
  1. Thêm `OCRError(RuntimeError)` có `code` (`ocr_unavailable`, `ocr_failed`, `page_limit`, `empty_document`); `PaddleOCR` bọc mọi exception (kể cả `ImportError`) thành `OCRError`.
  2. `extract_documents` bắt `OCRError` riêng, vẫn trả draft rỗng nhưng ghi thông báo vào state.
  3. `extract_for_quotation` đổi thông báo đó thành cảnh báo tiếng Việt riêng cho từng mã (vd. "Không đọc được nội dung file (OCR lỗi). Thử lại hoặc nhập tay." khác với "AI chưa trích xuất được dòng hàng").
- **CẦN DUYỆT**: thêm khóa `extraction_notices: list[{document, code, message}]` vào `ProcurementAgentState` (thay đổi contract state). Phương án thay thế không đổi state: `RecordingOCR` trong `intake.py` tự ghi lại `OCRError` nhưng `extract_documents` vẫn nuốt nó, nên chỉ làm được nếu OCR ném lỗi ra ngoài node (không khuyến nghị).
- Tiêu chí: thiếu `paddleocr` → API trả quotation với cảnh báo `ocr_unavailable`, không 500; PDF rỗng → cảnh báo `empty_document`.

### V6. Mất số trang và vị trí trong đường Paddle
- Nguyên nhân: `PaddleOCRHostedClient` bỏ trang `None` và không ghi `page_number`, nên LLM không thể trỏ đúng trang; không có bbox; `block_id` trong `extract_documents` là chuỗi tự ghép, không trỏ block OCR thật.
- Hướng giải quyết (giai đoạn 1, bắt buộc): luôn xuất `page_number` (theo thứ tự trang thật, trang `None` → `raw_text=""`) và `method`. Cùng schema JSON như nhánh text layer.
- Giai đoạn 2 (tùy chọn, **CẦN QUYẾT**): xuất thêm `blocks:[{block_id,text,bbox}]` từ output Paddle (`rec_texts` + `rec_polys`/`rec_boxes`) để provenance thật. Đánh đổi: tăng token gửi LLM và đụng mô hình `FieldSource`. Chỉ làm nếu UI cần highlight vị trí.

### V7. Cắt ngữ cảnh im lặng với Groq
- Nguyên nhân: `_fit_context_window` cắt ở 4500 token, chỉ thêm chuỗi `[TRUNCATED...]` vào prompt; người dùng không biết dòng hàng cuối có thể bị mất.
- Hướng giải quyết: khi cắt, ghi `extraction_notices` mã `ocr_truncated` (dùng chung kênh với V5) và hiển thị cảnh báo. Ưu tiên cắt theo ranh giới trang (bỏ cả trang cuối thay vì cắt giữa dòng) và ghi số trang bị bỏ.
- **CẦN QUYẾT**: chấp nhận cắt + cảnh báo, hay chia nhiều lượt gọi theo trang rồi gộp (tốn thêm token, đổi hành vi extractor và có thể đổi kết quả `make eval`)? Đề xuất bước này: chỉ cảnh báo.

### V8. Code chết và thiếu test
- `_serialize_result` và `_PaddleSDKClient`/`_PaddleModel` trong `ai_extraction.py` không còn dùng → xóa.
- Test cần thêm (không dùng Paddle thật, tiêm engine/module giả):
  - `TextFirstOCR`: toàn text; text + trang trống; text + trang scan; vượt giới hạn trang.
  - `PaddleOCRHostedClient`/`_extract_page_texts`: output kiểu v3 (dict `rec_texts`) và kiểu cũ (list); trang `None`; `ImportError` → `OCRError`.
  - Engine chỉ khởi tạo một lần.
  - `extract_documents`: `OCRError` → draft rỗng + `extraction_notices` đúng mã.
  - API/`extract_for_quotation`: mỗi mã lỗi cho đúng cảnh báo.

## 3. Thứ tự thực hiện (mỗi bước ≤ 1 commit)

| # | Bước | Vấn đề | Kiểm chứng |
|---|------|--------|------------|
| 0 | Spike chạy Paddle thật, ghi kết quả vào file plan | V3 | báo cáo kèm số liệu thời gian/RAM, **chờ duyệt** |
| 1 | `OCRError` + bọc lỗi Paddle + test | V5 (nửa đầu) | `pytest tests/test_extract_documents_v1.py` |
| 2 | Khóa `extraction_notices` + cảnh báo theo mã | V5, V7 | `pytest tests/test_api/test_procurement_integration.py` |
| 3 | Lazy engine dùng chung + setting `ocr_version`/`lang` | V3, V4 | test đếm khởi tạo |
| 4 | `TextFirstOCR` theo từng trang + giới hạn trang + `page_number`/`method` | V1, V2, V6 | test mới của `TextFirstOCR` |
| 5 | Cảnh báo cắt ngữ cảnh | V7 | test `_fit_context_window` + cảnh báo |
| 6 | Xóa code chết, cập nhật `ARCHITECTURE.md`/`AGENT.md` | V3, V8 | `ruff check`, `pytest` |

Sau bước 4 và 5 phải chạy `make eval` và ghi số liệu **trước/sau**, vì đầu vào của LLM thay đổi. Không được sửa đáp án kỳ vọng của `calculate_tco`/`compare_suppliers`, không xóa/skip/nới assert của test hiện có.

## 4. Rủi ro và giả định

- Giả định: paddleocr cài được trong môi trường chạy thật (hiện chưa xác minh được vì `.venv` trên máy dev thiếu `bin/python`).
- Rủi ro: OCR từng trang có thể cho văn bản khác OCR cả file (mất ngữ cảnh bảng nhiều trang) → phải đối chiếu bằng `make eval`.
- Rủi ro: thêm khóa state có thể ảnh hưởng checkpoint `MemorySaver`/các node khác đọc state (cần rà `src/agents/state.py`).

## 5. Tổng hợp việc cần bạn quyết

1. V2: từ chối hay cắt 10 trang đầu.
2. V3: nếu PP-OCRv5 kém tiếng Việt thì giữ v3 (sửa tài liệu) hay đổi engine; có dọn `paddleocr_access_token`/`base_url` không.
3. V5: duyệt thêm `extraction_notices` vào `ProcurementAgentState`.
4. V6: có làm `blocks`/bbox ở giai đoạn 2 không.
5. V7: chỉ cảnh báo hay chia lượt theo trang.
