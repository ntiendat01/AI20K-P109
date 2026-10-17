# AGENTS.md

## Tổng quan

Procurement Agent: trích xuất, kiểm tra và phân tích báo giá nhà cung cấp.
Stack: LangGraph (StateGraph), Qwen3-8B, PP-OCRv5, FastAPI.
Pattern: Orchestrator → Tool calling → Human-in-the-loop (HITL).

## Lệnh

- Cài đặt: `uv sync`
- Chạy dev: `uv run uvicorn src.api.main:app --reload`
- Kiểm tra tổng (chạy trước khi báo xong): `make check`
- Eval: `make eval`

## Cấu trúc

- `src/main.py` — composition root FastAPI, middleware và router registration.
- `src/api/` — HTTP transport: route, dependency và HTTP request/response.
- `src/application/` — use case/workflow điều phối nghiệp vụ và agent.
- `src/domain/` — Pydantic contracts cùng business rule thuần; là nguồn sự thật cho model mới.
- `src/agents/` — LangGraph graph, state, node và deterministic tool.
- `src/infrastructure/` — adapter OCR, LLM, PDF, repository và file/database.
- `src/core/` — Pydantic Settings, logging và technical primitive dùng chung.
- `eval/`        — datasets/ và scripts/
- `tests/`       — unit/, integration/, fixtures/ (dữ liệu ẩn danh)
- `docs/`        — specs/user-stories.md, adr/, diagrams/
- `ARCHITECTURE.md` — kiến trúc hệ thống (ở gốc repo)
- `tasks/`       — file task {ID}.md

## Quy ước code

- Python 3.11+, type hint cho hàm public; Pydantic cho mọi schema, không dict trần.
- Không hardcode prompt, model name, đường dẫn; đọc từ `src/core/config.py`.
- Log bằng `logging`, không `print`.

## Frontend style guide

- Mọi thay đổi giao diện phải tuân thủ [DotCom style guide](docs/STYLE_GUIDE.md).
- Chỉ dùng token typography đã định nghĩa trong `frontend/styles.css` và font
  Manrope. Không đặt `font-*` inline trong template JavaScript.

## Nguyên tắc 

- DRY (Don't Repeat Yourself): Không lặp lại mã nguồn
- KISS (Keep It Simple, Stupid): Giữ mã nguồn đơn giản nhất có thể
- YAGNI (You Aren't Gonna Need It): Không viết code cho những tính năng chưa cần thiết ở hiện tại
- Clean Code & Chuẩn đặt tên: Đặt tên biến, hàm rõ ràng, tường minh. Chia nhỏ module theo đúng trách nhiệm (Single Responsibility)

## Nguyên tắc vận hành và kỹ thuật
- Xử lý ngoại lệ (Defensive Programming): Luôn dự trù các tình huống bất thường, kiểm tra dữ liệu đầu vào (validation) và bẫy lỗi (try-catch)
- Ghi Log hiệu quả (Logging): Ghi lại các sự kiện quan trọng, lỗi hệ thống với mức độ (level) rõ ràng (Info, Warn, Error).
- Kiểm thử (Unit Test): Viết test cho các business logic quan trọng để đảm bảo không bị hỏng tính năng cũ khi cập nhật code mới.
- Bảo mật từ gốc (Security): Không bao giờ hardcode (để lộ) mật khẩu, API key hay thông tin nhạy cảm trong mã nguồn; luôn mã hóa dữ liệu quan trọng và chống các lỗi phổ biến như SQL Injection, XSS.

## Nguyên tắc phân chia các Hàm
- Áp dụng chữ S trong SOLID: Mỗi hàm chỉ làm đúng một việc duy nhất và làm thật tốt việc đó.
- Giữ hàm là một Pure Function: Một hàm được gọi là "pure" khi với cùng một đầu vào (input), nó luôn trả về một đầu ra (output) giống nhau và không gây ra tác dụng phụ (side-effects)

## Nguyên tắc phân chia Schema
- Tách biệt Domain (Nghiệp vụ) thay vì gộp chung:Chia schema theo từng cụm tính năng độc lập, Đừng cố nhét tất cả thông tin liên quan vào một bảng duy nhất
- Tách biệt loại dữ liệu theo tần suất đọc/ghi: Schema dữ liệu động (Transactional): Chứa dữ liệu thay đổi liên tục (giỏ hàng, số dư tài khoản). Cần tối ưu hóa để ghi nhanh, chính xác (đảm bảo tính ACID). Schema dữ liệu lịch sử/nhật ký (Log/Audit): Chứa dữ liệu chỉ ghi một lần và rất ít khi sửa (lịch sử đăng nhập, lịch sử thay đổi trạng thái đơn hàng). Cần tách riêng để tránh làm chậm các bảng dữ liệu động.

## Quy trình thực thi
Áp dụng cho task lớn (>3 file hoặc đổi contract). Task nhỏ: làm thẳng, vẫn chạy bước 4.

### 1. Chuẩn bị
- Làm trên nhánh riêng: `feature/{TASK_ID}-{mô-tả-ngắn}` hoặc `hotfix/{TASK_ID}-{mô-tả-ngắn}`.
- Đọc theo thứ tự: `ARCHITECTURE.md` → `/tasks/{TASK_ID}.md` → **chỉ** các file
  được liệt kê ở mục "Tài liệu liên quan" của task.
- Nếu spec thiếu, mâu thuẫn hoặc mơ hồ: **hỏi**, không tự đoán.

### 2. Lập plan (bắt buộc với task lớn)
- Trả về: danh sách file sẽ sửa/tạo, thứ tự thực hiện (mỗi bước ≤ 1 commit),
  thay đổi contract (nếu có), rủi ro và câu hỏi.
- **Dừng lại, chờ tôi duyệt. Không viết code trước khi được xác nhận.**

### 3. Thực hiện
- Từng bước nhỏ theo plan đã duyệt; không refactor ngoài phạm vi task.
- Viết/cập nhật test cùng lúc với code.
- Tuân thủ mục "Quy ước code" trong file này.
- Giao tiếp giữa các module theo contract trong `src/domain/`.

## Ranh giới kiến trúc

- `api` chỉ xử lý HTTP và gọi `application`; không gọi database/OCR/LLM trực tiếp.
- `application` điều phối use case, gọi `domain`, `agents` và adapter cần thiết.
- `domain` không import FastAPI, LangGraph, database, OCR, LLM hay filesystem.
- `infrastructure` cài đặt chi tiết kỹ thuật và có thể import contract từ `domain`.
- Contract nghiệp vụ nằm trong `src/domain/`; HTTP request/response nằm trong `src/api/contracts/`. Không tạo lại các namespace `src/models`, `src/services`, `src/extraction` hoặc `src/ocr`.

### 4. Kiểm tra (bắt buộc trước khi báo xong)
- Chạy `make check`.
- Nếu fail: sửa nguyên nhân gốc và chạy lại.
  **Không** xóa, skip hay nới test để cho pass.
- Kẹt sau 3 lần thử: dừng và báo cáo, không đoán tiếp.

### 5. Kết thúc
- Commit theo Conventional Commits (`feat(extract): ...`).
- Đổi trạng thái task thành `In Review` (không tự đặt `Done`).
- Sửa schema/contract/spec: **chỉ khi đã được duyệt**.
- Báo cáo cuối: file đã đổi, lệnh đã chạy + kết quả, giả định đã đặt,
  phần chưa làm.

## Ranh giới

### Luôn làm
- Làm trên nhánh riêng, commit sau mỗi bước nhỏ.
- Chạy `make check` trước khi báo xong.
- Giữ diff nhỏ, chỉ sửa file thuộc phạm vi task.

### Hỏi trước
- Thêm dependency, đổi schema/contract, đổi public API.
- Sửa quá 5 file hoặc thêm thư mục mới ngoài plan đã duyệt.
- Đổi prompt hoặc logic tool (kèm `make eval` trước/sau).

### Không bao giờ
- Sửa `.env*`, commit secret, `git push`, `git reset --hard`, `git clean`.
- Sửa file được bảo vệ: `eval/datasets/`, baseline, `Makefile`, `.github/`,
  `.claude/settings.json`. Cần đổi thì đề xuất, chờ tôi làm.
- Xóa, skip hoặc nới test/assert để cho pass.

## Tài liệu (đọc khi cần)
- Kiến trúc: ARCHITECTURE.md (luôn đọc trước khi làm task)
- User story: docs/specs/user-stories.md (khi task ghi US-ID, chỉ đọc story đó)
- Quyết định thiết kế: docs/adr/ (khi task trỏ tới)
