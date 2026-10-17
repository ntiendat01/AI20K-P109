Dự án P-109 (Procura) là một repo duy nhất, chạy trong một tiến trình Python: FastAPI phục vụ cả API lẫn FE, còn agent LangGraph được gọi nội bộ. Mình chưa chạy code và không sửa gì trong repo. Mình chưa đọc hết styles.css, các màn hình FE phụ, src/services/quotation/* và src/extraction/*.

Frontend

FE là HTML/CSS/JS thuần dùng ES modules, không có framework hay bước build.

Cấu trúc: app.js khôi phục session rồi giao cho core/router.js. Router điều hướng theo hash tới các màn hình trong features/ (workspace, PR, báo giá, so sánh, phê duyệt, lịch sử, PO). Phân quyền theo hai vai trò: procurement (Nhân viên mua sắm) và manager (Quản lý duyệt).
Gọi API: core/api.js gắn Bearer token và gọi /api/v1. Session lưu trong localStorage.
Phân tích: màn so sánh gọi POST /prs/{id}/analysis, rồi poll GET mỗi 2 giây, tối đa 6 phút. Sau đó FE lấy /recommendations/{id}/review và gửi feedback qua /recommendations/{id}/feedback.
Lỗi Docker: frontend/Dockerfile chỉ copy index.html, styles.css, app.js. Thư mục core/, features/, config/, utils/ không có trong image, nên image nginx sẽ lỗi import ngay khi tải trang. Hiện chạy được vì backend mount ./frontend và phục vụ ở /ui/.
Cần kiểm tra: execute_analysis đặt trạng thái awaiting_buyer_review, còn comparison.js so với awaiting_review. Có thể bước evaluation đổi trạng thái ở giữa, nhưng mình chưa xác nhận.
Backend
Khởi động: src/main.py mount các router (/api/v1, /api) và /ui. Lifespan khởi tạo ProcurementWorkflow rồi reconcile PR, báo giá, PO. Có middleware request-id, log không ghi body hay query, và tắt cache UI ở môi trường dev.
Nhóm API: auth, PR, báo giá (upload, re-extract, confirm, xem file nguồn), approve/reject, PO, analysis, recommendations và evaluations.
Phân tích bất đồng bộ: POST /prs/{id}/analysis lưu snapshot rồi trả 202, sau đó chạy graph bằng asyncio.create_task. Nếu thiếu trường bắt buộc thì trả 422. Nếu dữ liệu PR hoặc báo giá đổi sau snapshot thì trả stale. Task nền chỉ sống trong process, nên restart giữa chừng thì run kẹt. Có _recover_expired_running để xử lý.
Lưu trữ: JSON trong data/ cho PR, báo giá, PO. SQLite cho workflow và evaluation, Chroma cho evidence.
Evaluation sau quyết định: services/evaluation/ có engine, grounding, validation và store, tối đa 2 lần tự sửa. Mục đích là kiểm chứng đề xuất của LLM bằng nguồn trước khi buyer duyệt.
Di sản còn lại:
POST /api/v1/chat gọi agent.ainvoke({"query": ...}) trên graph procurement, sẽ không chạy đúng.
/prs/{id}/comparison và hai route /analyze, /decision-pipeline đã deprecated.
Trước đây có hai model root song song là `models/` và `models_v1/`; strict agent contract hiện đã chuyển vào `src/models/agent`.
Agent (LangGraph)

Graph nằm ở src/agents/graph.py với state ProcurementAgentState. Luồng thực tế:

extract_documents → validate_extraction → [confidence_router]
   mandatory → human_review_extraction (interrupt) → normalize
   optional  → normalize
normalize → check_data_ready → (unconfirmed: END | ready: begin_analysis)
begin_analysis → calculate_tco → compare_suppliers ┐
              → analyze_risks ─────────────────────┴→ decision_llm
decision_llm → human_review_recommendation (interrupt) → END
Phần tất định: calculate_tco, compare_suppliers và analyze_risks không gọi LLM. TCO dùng Decimal và làm tròn HALF_UP. Ngưỡng lệch so sánh là 15%.
Phần LLM: chỉ decision_llm gọi model. Nó chặn các đề xuất tham chiếu ngoài snapshot: ranking phải đủ top_n, không trùng, phần tử đầu là preferred, mọi supplier phải nằm trong tập hợp lệ. Vi phạm thì trả NEEDS_INPUT. Thiếu provider hoặc JSON hỏng cũng trả NEEDS_INPUT.
Cách BE dùng graph: BE gọi build_graph(confirmed_input=True), bỏ qua bước extract vì FE đã xác nhận báo giá. Graph chạy bằng MemorySaver, mất khi restart, và thread_id là analysis_id.
Lệch so với ARCHITECTURE.md:
process_feedback và generate_evidence không còn trong graph. Vòng revise không nằm trong graph, evidence do services/evaluation xử lý.
evaluate_sufficiency chỉ còn nằm trong evaluate.py mà không được nối vào graph.
Đường dẫn file trong ARCHITECTURE.md và AGENT.md (src/agent/, src/schemas/, src/api/main.py) không khớp cấu trúc thật (src/agents/, src/models/agent/, src/main.py).
Hai điểm khác khi so với ARCHITECTURE.md/AGENT.md: AGENTS.md mà CLAUDE.md tham chiếu không tồn tại, file thật là AGENT.md. make check hiện chạy lint format test và không có typecheck.
Observability

LangSmith tracing dùng trực tiếp biến môi trường LangChain/LangSmith và các decorator `@traceable` ở luồng trích xuất. Package `monitor/` và stack Langfuse demo đã bị loại bỏ vì không được kết nối vào runtime thật; không còn callback facade hay mock simulator.
Đề xuất bước tiếp theo
Sửa frontend/Dockerfile để copy đủ thư mục FE, hoặc bỏ image nginx nếu chỉ phục vụ qua backend.
Dọn /chat, các route deprecated và models/old/. Đồng bộ ARCHITECTURE.md, AGENT.md với code thật.
