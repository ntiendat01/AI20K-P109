# Hướng dẫn Cấu hình Monitor (Bổ sung): Luồng Evaluate to End

Tài liệu này bổ sung cho `monitor_platform_setup_guide.md`, tập trung vào việc giám sát và đánh giá chất lượng cho nửa sau của đồ thị (từ node `evaluate` đến `END`), sau khi áp dụng kiến trúc chuẩn cho **Sufficiency Rubric** và **Evidence Grounding**.

---

## 1. Cấu hình DeepEval (Sufficiency Metrics)

Vì node `evaluate` không chỉ đếm số lượng báo giá mà phải thực hiện chấm điểm (rubric) quyết định của LLM, chúng ta cần tích hợp **DeepEval** và kết nối nó với hệ thống telemetry hiện tại.

### Cập nhật `.env`
Bổ sung các key cần thiết để DeepEval đẩy kết quả về trung tâm:
```env
DEEPEVAL_TELEMETRY_API_KEY=<your-deepeval-key>
# Đảm bảo DeepEval ghi log chung session với Langfuse
LANGFUSE_ENABLE_DEEPEVAL_INTEGRATION=true
```

### Dashboard Setup (DeepEval Confident Cloud)
- **Custom Metrics Dashboard:** Tạo một dashboard theo dõi 3 tiêu chí cốt lõi của node `evaluate`:
  1. `Completeness Score` (LLM có recommend đủ Top N không?)
  2. `Justification Score` (Lý do có hợp logic tài chính không?)
  3. `Risk Tolerance Score` (Mức độ vi phạm rủi ro)
- Thiết lập **Alert (Webhook)**: Nếu `Risk Tolerance Score` rơi xuống dưới `0.5`, lập tức gửi thông báo Slack cho team QA.

---

## 2. Theo dõi Evidence Grounding (ChromaDB & RAG Tracing)

Luồng `generate_evidence` mới sẽ sử dụng Vector DB (ChromaDB) để tìm kiếm gốc của dữ liệu (Context Grounding) thay vì dùng Regex.

### LangSmith: Tracing Retrieval Steps
Node `generate_evidence` nay đã biến thành một luồng RAG. Trên **LangSmith**:
- Các bước tìm kiếm (Retrieval) phải được gắn tag `type: "retriever"`.
- Trên giao diện LangSmith, hãy tạo filter: `has_tag: "evidence_retrieval" AND has_metadata: {"low_confidence": true}`.
- Lưu filter này lại thành **"Hallucination Watch"**. Bất cứ khi nào Vector DB không tìm thấy context khớp với số liệu LLM bịa ra, trace sẽ rơi vào đây.

---

## 3. Langfuse: Quản lý Feedback Loop (HITL-2)

Tại node `human_review_recommendation` (HITL-2) và `process_feedback`, chúng ta cần theo dõi hành vi của Procurement Manager.

### Đính kèm Feedback trực tiếp vào Trace
Trong `monitor/adapters/langfuse_adapter.py`, khi xử lý event `log_revision_loop`, hãy sử dụng tính năng **Generations feedback** của Langfuse.
- Thay vì chỉ đếm số lần revise, hãy attach trực tiếp chuỗi feedback của manager (vd: *"Cần tìm vendor có bảo hành tốt hơn"*) vào chính cái `generation_id` của LLM đã tạo ra bảng xếp hạng đó.
- Việc này giúp giao diện Langfuse hiển thị nút 👍 / 👎 kèm theo Text Feedback ngay dưới output của LLM.

### Phân tích Mức độ Chấp nhận (First-Time Acceptance Rate)
- Trên Langfuse Dashboard, sử dụng tính năng **Analytics -> Conversion**.
- Thiết lập phễu (Funnel): `Session Start` -> `Decision LLM Generated` -> `Hit END directly (No Revise)`.
- Chỉ số này chính là KPI quan trọng nhất của Agent: Tỷ lệ Manager đồng ý ngay lần đầu tiên mà không yêu cầu revise.

---

## 4. Kiểm tra Giả lập (Simulator Updates)

Cần cập nhật script `mock_simulator.py` để mô phỏng luồng mới:
1. Mô phỏng **DeepEval** trả về điểm `Justification Score = 0.4` (Dẫn đến `evaluate_sufficiency` đánh fail và thoát sớm).
2. Mô phỏng **ChromaDB** không tìm thấy số liệu chứng minh (Dẫn đến `generate_evidence` set `low_confidence = True`).
3. Xác minh LangSmith bắt được tag `"evidence_retrieval"` và Langfuse hiển thị đúng Session Grouping kể cả khi bị fail giữa chừng.
