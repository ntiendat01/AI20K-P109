graph TB
    subgraph ClientLayer["1. PRESENTATION LAYER (Giao diện Người dùng)"]
        UI_Buyer["🧑‍💼 Buyer (Nhân viên Mua hàng)• Tạo PR & Upload Báo giá PDF• Rà soát & Xác thực bóc tách (HITL-1)"]
        UI_Manager["👨‍💼 Manager (Quản lý Phê duyệt)• Xem Ma trận so sánh & Đề xuất AI• Phê duyệt / Từ chối / Yêu cầu sửa (HITL-2)"]
        Web_App["🖥️ Web Client (Single Page App)Vanilla HTML5 / Modern CSS / JavaScript"]
        UI_Buyer --> Web_App
        UI_Manager --> Web_App
    end

    subgraph APILayer["2. BACKEND API SERVICE (FastAPI - Python)"]
        Auth_Module["🔐 Auth & RBAC Module(JWT, Phân quyền Buyer/Manager)"]
        PR_Route["📋 PR & Quotation Routes(/api/v1/prs, /api/v1/quotations)"]
        Workflow_Route["⚡ Workflow & Analysis Routes(/api/v1/prs/{id}/analysis)"]
        PO_Route["📦 Purchase Order Routes(/api/v1/purchase-orders, /feedback)"]

        Web_App -->|HTTP/REST| PR_Route
        Web_App -->|HTTP/REST| Workflow_Route
        Web_App -->|HTTP/REST| PO_Route
    end

    subgraph AgentLayer["3. AI AGENTIC ORCHESTRATION (LangGraph Engine)"]
        subgraph Phase1["PHASE 1: Document Intake (HITL-1)"]
            OCR_Engine["👁️ Text-First OCR(PyMuPDF / OCR service)"]
            Extract_LLM["📝 Extraction LLM(Bóc tách cấu trúc Báo giá JSON)"]
            **~~Validate_Node["🛡️ Validate Extraction~~****~~(Kiểm tra trường dữ liệu)"]~~**
            HITL1_Node["⏸️ Checkpoint HITL-1(Tạm dừng chờ Buyer xác nhận)"]

            OCR_Engine --> Extract_LLM ~~--> Validate_Node~~ --> HITL1_Node
        end

        subgraph Phase2["PHASE 2: Procurement Analysis & Decision (HITL-2)"]
            Normalize_Node["🔄 Normalization Tool(Quy chuẩn Đơn vị tính & Tiền tệ)"]
            TCO_Tool["🧮 Deterministic TCO Calculator(Tính Tổng chi phí sở hữu tuyệt đối)"]
            Matrix_Tool["📊 Comparison Matrix Tool(So sánh: TCO, Lead time, Bảo hành)"]
            Decision_Node["🧠 Decision LLM(Đề xuất NCC tối ưu & Lập luận)"]
            ~~Eval_Node["🔍 Grounding & Evidence Evaluator~~~~(Đối soát RAG chống Hallucination)"]~~

            Normalize_Node --> TCO_Tool --> Matrix_Tool --> Decision_Node [~~--> Eval_Node~~]()
        end

        PR_Route --> Phase1
        Workflow_Route --> Phase2
    end

    subgraph ExternalAI["4. EXTERNAL AI PROVIDERS"] (thử, chưa biết con nào ngon)
        Groq_API["⚡ Groq API(openai/gpt-oss-20b)"]
        OpenAI_API["🌐 OpenAI API(gpt-6-luna)"]
        Paddle_API["📑 PaddleOCR service"]

        Extract_LLM -.-> Groq_API
        Decision_Node -.-> Groq_API
        OCR_Engine -.-> Paddle_API
    end

    subgraph StorageLayer["5. PERSISTENCE & DATA STORAGE LAYER"]
        Upload_Dir[("📁 File Storagedata/uploads/ (*.pdf)")]
        Workflow_DB[("🗄️ Workflow SQLiteanalysis, finalization")]
        Eval_DB[("🗄️ Evaluation SQLiterecommendations, versions")]
        Chroma_DB[("🔮 Vector Database (ChromaDB)RAG Evidence Chunks")]
        Repo_JSON[("📄 Data Repositories (JSON)PRs, Quotations, POs")]

        PR_Route --> Upload_Dir
        Workflow_Route --> Workflow_DB
        Eval_Node --> Eval_DB
        Workflow_Route --> Chroma_DB
        PO_Route --> Repo_JSON
    end

    classDef client fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef api fill:#ede7f6,stroke:#512da8,stroke-width:2px;
    classDef agent fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef db fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef ext fill:#fce4ec,stroke:#c2185b,stroke-width:2px;

    class UI_Buyer,UI_Manager,Web_App client;
    class Auth_Module,PR_Route,Workflow_Route,PO_Route api;
    class OCR_Engine,Extract_LLM,Validate_Node,HITL1_Node,Normalize_Node,TCO_Tool,Matrix_Tool,Decision_Node,Eval_Node agent;
    class Upload_Dir,Workflow_DB,Eval_DB,Chroma_DB,Repo_JSON db;
    class Groq_API,OpenAI_API,Paddle_API ext;
