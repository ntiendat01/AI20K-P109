# Evaluation sau Decision LLM — triển khai

Trạng thái: **In Review**. Theo [spec](specs/evaluation-after-decision-llm.md), thực hiện thứ tự mục 11.

## Các phần đã nối

1. `src/models/evaluation.py`: contracts tách proposal không tin cậy khỏi runtime context, source/evidence, evaluation và feedback. Unknown dùng `None`, không dùng 0. Field ngoài schema bị từ chối.
2. `tests/fixtures/evaluation/`: proposal nguyên mẫu trong spec và oracle ẩn danh. Các phép so sánh có đáp án tính tay: 12000 < 14500; 5 < 7; 24 > 12.
3. `evaluation_validation.py`: decision/reference inventory, hard/soft constraint outcomes, no viable và missing fact.
4. `evaluation_evidence.py`: ingestion Chunk metadata, Query riêng từng claim/NCC, Get exact records, filter tenant/case/document/hash, một lượt expansion parent/context/original. Không đọc quote text từ graph state.
5. `evaluation_grounding.py`: kiểm nguồn nguyên văn, metadata/hash, literal label/value/unit, điều kiện và time origin, Decimal replay theo formula server, comparison full scope/ties, counter-evidence, human edit đã được application xác thực.
6. `evaluation.py`: năm gates theo thứ tự, bảy check catalog, quality 0–4 theo từng dimension, action precedence, retry dịch vụ có backoff. Không có LLM judge mở cổng mandatory checks.
7. `evaluation_store.py` + `evaluation_workflow.py`: SQLite lưu proposal/context/evaluation theo version, trạng thái review, counters, feedback và audit. Transaction `BEGIN IMMEDIATE` + compare-and-set chặn stale/concurrent finalization. Cùng idempotency key/payload/actor trả receipt cũ; payload hoặc actor khác trả conflict. Reject/close là terminal.
8. `scripts/evaluate_post_decision.py`: đo offline, lưu [kết quả JSON](evaluation-acceptance-results.json). Chưa tối ưu k/cache/concurrency.

## Dependency injection khi chạy ứng dụng

Context và quyền là dependency của ứng dụng như mục 2 spec; không suy ra từ LLM, request body, raw extraction hay tài liệu. Ứng dụng gọi trong startup:

```python
from src.api.routes.evaluation import configure_evaluation
from src.agents.nodes.decision_llm import DecisionOutputRepair
from src.services.llm import get_llm

workflow = configure_evaluation(
    app,
    collection=authorized_chroma_collection,
    context_provider=load_runtime_context,  # (case_id, authenticated_actor) -> RuntimeEvaluationContext
    repair_model=DecisionOutputRepair(get_llm()),  # bỏ qua nếu muốn xử lý repair bằng worker riêng
)
```

Authentication middleware phải đặt `request.state.actor` bằng `Actor` lấy từ phiên đã xác thực. Không nhận actor/roles/timestamp từ body hoặc header do client tự khai. Context provider cấp candidate scope, facts đã xác thực cho feasibility, rules/constraints, source revisions, comparison bắt buộc, calculation plans và version hiện hành. Trường `authorized_edit_ids` chỉ chứa audit edits đã xác thực. `Rule.exception_authorized` cũng chỉ do application cấp sau khi kiểm authority.

Không có runtime provider/collection: API trả 503. Không có actor: 401. Không đủ quyền: 403. Conflict/stale version: 409. Không tự tạo policy hay quyền mặc định để mở approval.

Settings nằm trong `src/config.py`: `evaluation_database_path`, `evidence_query_k`, `evidence_service_retries`, `evidence_retry_backoff_seconds`. Chroma dependency được khai báo trong `requirements.txt`; embedding function là cấu hình của collection do ứng dụng sở hữu.

## Điểm vào và HITL-2

- `POST /api/evaluations/cases/{case_id}` nhận `{"proposal": ...}`; runtime context được load phía server. Output sai schema trở thành `REPAIR_OUTPUT`.
- `GET /api/evaluations/{recommendation_id}/review` chỉ mở khi current version đang `awaiting_review` và actor đủ quyền.
- `POST /api/evaluations/{recommendation_id}/feedback` nhận contract `Feedback` của spec, với `decision` là `approve|reject|revise|close`.
- `POST /api/prs/{case_id}/analyze` dùng graph mới, trả `AnalysisRunResponse` với evaluation/status/ID/version; **không còn auto-approve HITL-2**. Client cũ cần dùng endpoint review thay vì đọc `status=completed` như một phê duyệt.

Graph dùng `decision_proposal` để lấy full contract; không sử dụng fallback ranking/citation cũ. `build_graph(evaluation_workflow=..., context_provider=...)` cũng dùng được trực tiếp. Các hàm legacy vẫn giữ cho compatibility module, nhưng không thuộc đường graph production.

HITL-2 là boundary bền vững trong SQLite, không phải LangGraph interrupt. Khởi động lại workflow với cùng database có thể đọc review và approve/reject mà không gọi lại LLM/Chroma. MemorySaver chỉ còn dùng cho phần graph upstream/HITL-1, ngoài phạm vi spec này.

`revise/explanation_change` trả route `repair_decision_llm`, status `awaiting_repair`. Worker có thể dùng `DecisionOutputRepair.revise` với feedback đã lưu, rồi submit output mới cùng version mới. `preference_change`, `data_correction`, `rule_change` và mixed trả route owner tương ứng; downstream không tự áp dụng các thay đổi này. Owner gọi `mark_feedback_applied` sau khi thật sự áp dụng change set và version mới qua toàn bộ evaluation. Việc đưa note vào prompt không tự đặt feedback applied.

Automatic repair của evaluator có tối đa hai lần trên recommendation, dừng sớm khi output/issue không tiến triển. Mỗi output mới có version mới, evidence/evaluation mới. Buyer revisions và service retries có counters/budgets riêng. Không có repair adapter thì trả action để worker xử lý, không tự gọi model chưa được cấu hình.

## Cách hiển thị an toàn và giới hạn verifier

Review renderer tạo facts từ predicates đã được kiểm và evidence artifacts. Không xuất summary/rationale/trade-off prose tự do thành factual UI text. Negotiation được gắn nhãn suggestion, không phải cam kết NCC. Inventory kiểm reference graph và numerical assertions; không coi kiểm token là chứng minh ngữ nghĩa toàn bộ văn xuôi. Khi bổ sung UI, phải dùng payload renderer này, không render lại raw proposal lưu trong database.

Source verifier hiện hỗ trợ literal label/value/unit theo allowlist EN/VI trong `METRIC_LABELS`/`UNIT_LABELS`, cùng conditions/time origin. Không dùng một số bất kỳ xuất hiện đâu đó trong chunk để chứng minh metric. Dạng nguồn không khớp, thiếu header/locator/operand hoặc điều kiện chưa xác định sẽ unresolved/request data; cần mở rộng parser có tests khi corpus có format khác. Ingestion và tạo facts từ OCR/PDF vẫn thuộc upstream, không nằm trong thay đổi này. Derived TCO chỉ dùng phép cộng các components đã khai thuế trong allowlist; không đoán VAT/fee thiếu.

## Kiểm chứng

```bash
PATH="$PWD/.venv/bin:$PATH" make check
.venv/bin/python -m scripts.evaluate_post_decision --output docs/evaluation-acceptance-results.json
```

`make eval` hiện không có recipe trong Makefile; lệnh trả “Nothing to be done” do thư mục `eval/` tồn tại. Không thay đổi Makefile được bảo vệ. Script trên là phép đo riêng cho downstream.

Test integration dùng ChromaDB thật cục bộ, embedding cố định, không tải model hoặc gọi API ngoài. Bộ benchmark JSON dùng fake theo API Query/Get để đo riêng evaluator; 240 lần chạy trên 6 đầu vào, không phải 240 ca độc lập. False-support được đếm trên claim bị cố ý làm sai/thiếu nguồn. Kết quả không đại diện latency/recall corpus production.

Kết quả kiểm tra: **170 tests passed**, lint/format pass. Benchmark ghi nhận **0/200 false-support** trên targeted corrupted/missing claims; repair không tiến triển dừng sau một lần gọi. Giá trị p50/p95 nằm trong JSON và có thể dao động giữa các lượt chạy.

Trước thay đổi: 109 test pass, 13 fail trong fixture graph cũ thiếu `extraction_id`. Fixture đã được cập nhật theo contract canonical và kiểm thử được chuyển sang hành vi HITL-2 có authority/version/persistence; không nới điều kiện nguồn hoặc approval để qua test. `make check` cũng chuẩn hóa format một số file cũ; logic TCO/comparison không thay đổi.

Tham chiếu adapter: [Chroma Query/Get](https://docs.trychroma.com/docs/querying-collections/query-and-get), [metadata filtering](https://docs.trychroma.com/docs/querying-collections/metadata-filtering).
