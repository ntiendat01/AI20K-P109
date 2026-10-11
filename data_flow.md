
sequenceDiagram
    autonumber
    actor Buyer as 🧑‍💼 Buyer
    participant UI as 🖥️ Frontend Web
    participant API as 🚀 FastAPI Backend
    participant Intake as 📑 Intake Agent (LangGraph Phase 1)
    participant LLM as 🤖 LLM (Groq / OpenAI)
    participant Workflow as 🧠 Workflow Agent (LangGraph Phase 2)
    participant Chroma as 🔮 ChromaDB (Evidence Store)
    actor Manager as 👨‍💼 Manager

    %% GIAI ĐOẠN 1: INTAKE & HITL-1
    rect rgb(240, 248, 255)
    note over Buyer, Intake: GIAI ĐOẠN 1: BÓC TÁCH BÁO GIÁ & XÁC NHẬN DỮ LIỆU (HITL-1)
    Buyer->>UI: Upload các file PDF báo giá + Nhập thông tin PR
    UI->>API: POST /api/v1/prs/{id}/quotations (Multipart PDF)
    API->>Intake: Gọi extract_for_quotation(file_path)
    Intake->>Intake: TextFirstOCR (PyMuPDF -> PaddleOCR)
    Intake->>LLM: Gửi văn bản OCR + Prompt trích xuất
    LLM-->>Intake: Trả về JSON (items, đơn giá, VAT, phí ship, lead time, bảo hành)
    Intake-->>API: Trả về kết quả trích xuất sơ bộ (Chưa duyệt)
    API-->>UI: Hiển thị bảng đối soát dữ liệu (Pending Review)
    Buyer->>UI: Rà soát, hiệu chỉnh số liệu & Bấm "Xác nhận báo giá"
    UI->>API: POST /quotations/{id}/confirm (QuotationConfirmation)
    API->>Intake: resume_confirmation() -> Gắn nhãn confirmed_by_human = True
    end

    %% GIAI ĐOẠN 2: ANALYSIS & COMPARISON
    rect rgb(245, 255, 245)
    note over Buyer, Chroma: GIAI ĐOẠN 2: SO SÁNH, TÍNH TCO & CHẠY AGENT ĐỀ XUẤT
    Buyer->>UI: Bấm "Mở bảng so sánh & Đề xuất AI"
    UI->>API: POST /api/v1/prs/{id}/analysis
    API->>Workflow: prepare() -> Lập Snapshot Revision & Hash tài liệu
    Workflow->>Chroma: Ingest Evidence Chunks (Gốc & Edit) để làm căn cứ đối soát
    Workflow->>Workflow: Chuẩn hóa UOM & Tiền tệ (normalize_data)
    Workflow->>Workflow: Tính toán TCO chính xác bằng công thức code (calculate_tco)
    Workflow->>Workflow: Lập Ma trận so sánh 3 tiêu chí: TCO, Lead time, Bảo hành
    Workflow->>LLM: Gửi ma trận so sánh -> Đề xuất NCC tối ưu nhất (decision_llm)
    LLM-->>Workflow: Trả về DecisionProposal (preferred_supplier, lý do, trade-offs)
    ~~Workflow->>Chroma: Đối soát bằng chứng (Verification) chống Hallucination~~
    Workflow-->>API: Lưu kết quả phân tích vào SQLite (status: awaiting_review)
    API-->>UI: Render Ma trận so sánh, biểu đồ TCO & Đề xuất của AI
    end

    %% GIAI ĐOẠN 3: HITL-2 & PO FINALIZATION
    rect rgb(255, 250, 240)
    note over Manager, API: GIAI ĐOẠN 3: QUẢN LÝ DUYỆT ĐỀ XUẤT & PHÁT HÀNH ĐƠN PO (HITL-2)
    Manager->>UI: Đăng nhập quyền Quản lý, xem xét đề xuất & lý giải AI
    alt Trường hợp Phê duyệt (Approve)
        Manager->>UI: Bấm "Phê duyệt" (Approve) kèm ghi chú
        UI->>API: POST /api/v1/evaluation/feedback (decision: "approve")
        API->>Workflow: approval_command() & finalize()
        Workflow->>Workflow: Tạo mã PO, gán NCC chiến thắng, chốt tổng tiền gồm thuế
        Workflow-->>API: Lưu PurchaseOrder vào DB & cập nhật PR -> "approved"
        API-->>UI: Hiển thị Đơn mua hàng PO hoàn tất (Sẵn sàng in/gửi NCC)
    else Trường hợp Yêu cầu điều chỉnh (Revise)
        Manager->>UI: Bấm "Yêu cầu chỉnh sửa" (Revise)
        UI->>API: POST /evaluation/feedback (decision: "revise")
        API->>Workflow: Ghi nhận pending_feedback để Agent phân tích lại
    end
    end
