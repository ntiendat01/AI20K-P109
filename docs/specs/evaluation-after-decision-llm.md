# Thiết kế evaluation sau Decision LLM

Ngày: 01/10/2026. Trạng thái: thiết kế đề xuất.

## 1. Phạm vi

Tài liệu này chỉ thiết kế đoạn workflow bắt đầu khi `decision_llm` đã trả proposal và kết thúc tại quyết định của buyer. Không dùng snapshot, không mô tả extraction, normalization, tool calling hoặc cách tạo dữ liệu đầu vào cho Decision LLM.

Các thành phần được giữ:

- Output LLM có cấu trúc gồm ranking, claims, comparison, risks, uncertainties, trade-offs và negotiation points.
- Evaluation theo năm tầng: **Decision validation → Constraint validation → Evidence-grounding validation → Business-rule validation → Recommendation quality evaluation**.
- Evidence Node dùng ChromaDB để truy hồi chunk gốc từ rationale và atomic claims.
- Action/route rõ ràng cho repair, thiếu dữ liệu, ngoại lệ, lỗi kỹ thuật, approve, revise và reject.
- Human feedback có kiểu, version và idempotency key.

## 2. Ranh giới đầu vào của Evaluation

Evaluation nhận hai input riêng:

1. **Decision LLM output**: proposal không đáng tin cậy, cần được kiểm tra.
2. **Runtime evaluation context**: dữ liệu tin cậy do application cấp trong lúc chạy, không lấy từ LLM. Nó chỉ gồm case ID, recommendation ID/version, candidate IDs trong scope, constraints/rules đang áp dụng, danh sách comparison bắt buộc, formula allowlist và source scope được phép truy cập.

Runtime context không phải artifact thiết kế của workflow này. Nó là dependency injected vào evaluator để evaluator có thể kiểm các phép so sánh, business rules và nguồn evidence. LLM không được đọc/ghi quyền truy cập, candidate scope, constraint, rule, phiên bản hay trạng thái approval.

| Dữ liệu | Bên sở hữu | Evaluation dùng để |
| --- | --- | --- |
| Proposal, rationale, claims, trade-offs | Decision LLM | Đối tượng cần kiểm tra |
| Recommendation ID/version, case ID | Application | Chống stale approval và truy vết |
| Candidate scope, hard/soft constraints, rules | Application | Kiểm feasibility, fairness và quy trình |
| Chroma source scope | Application | Giới hạn truy hồi đúng case/tài liệu/revision |
| Formula allowlist | Application | Replay calculation có kiểm soát |
| Evidence artifacts, issue/action, review decision | Evaluator/Application | Điều phối bước sau và audit |

## 3. Flow sau Decision LLM

```mermaid
flowchart TD
    L["Decision LLM output"] --> D["1. Decision validation"]
    D --> C["2. Constraint validation"]
    C --> E["Evidence Node: ChromaDB retrieval"]
    E --> G["3. Evidence-grounding validation"]
    G --> B["4. Business-rule validation"]
    B --> Q["5. Recommendation quality evaluation"]
    Q --> H["HITL-2: Buyer review"]

    D -. "repairable" .-> R["Repair Decision LLM"]
    C -. "missing fact / no viable" .-> W["Awaiting input or resolution"]
    G -. "optional claim unsupported" .-> R
    G -. "mandatory source unresolved" .-> W
    B -. "exception required" .-> X["Awaiting authorized exception"]
    Q -. "quality repairable" .-> R

    R --> L
    H -- "approve" --> A["Approved → END"]
    H -- "reject" --> J["Rejected → END"]
    H -- "revise: explanation" --> R
    H -- "revise: data/preference/rule" --> W
```

Evidence retrieval là bước chuẩn bị cho grounding validation, không tự cấp trạng thái verified. Các nhánh `Awaiting input or resolution` nằm ngoài phạm vi downstream: sau khi dữ liệu/rule/ưu tiên được xử lý ở nơi sở hữu chúng, workflow chỉ nhận một output mới từ `decision_llm` và bắt đầu lại tại Decision validation.

## 4. Contract output đầy đủ của Decision LLM

### 4.1. Nguyên tắc

Mọi fact xuất hiện trong summary, rationale, risk, trade-off, assumption hoặc negotiation point phải được khai báo thành claim có ID. Rationale là bản nháp; UI cuối chỉ hiển thị factual claims đã qua grounding.

LLM không sinh hoặc thay đổi các trường sau: `recommendation_id`, `recommendation_version`, approval state, evaluation state, feedback history, evidence verdict, authority hoặc application errors. Application bọc output trong envelope có hai ID/version này.

`evidence` trong ranked item luôn bắt đầu rỗng. Evidence Node là nơi duy nhất tạo citation/source excerpt.

### 4.2. Schema logic

| Nhóm | Bắt buộc | Mục đích |
| --- | --- | --- |
| `decision` | Có | Kiểu kết quả, preferred supplier, summary và reasons. |
| `recommendation` | Có | Top-N, ranked list, shortfall nếu có ít candidates hơn Top-N. |
| `claims` | Có | Atomic factual/comparative assertions để evidence verifier xử lý. |
| `comparisons` | Có khi ranking | Scope, metric, supplier IDs và claims so sánh. |
| `trade_offs` | Có khi có alternative material | Giá trị nhận được/mất đi khi chọn phương án. |
| `negotiation_points` | Có thể rỗng | Suggestions, không phải cam kết của NCC. |
| `risk_flags` | Có | Risks với knowledge status, không tự đánh giá pass/fail. |
| `uncertainties` | Có | Unknown, tác động và action đề xuất. |
| `open_questions`, `assumptions` | Có thể rỗng | Việc buyer cần làm và giả định được phép. |

`decision.type` chỉ nhận một trong: `ranked_recommendation`, `no_viable_supplier`, `insufficient_candidates`, `needs_input`. Ba loại không ranking phải có `ranked: []` và `preferred_supplier_id: null`.

Claim là discriminated union:

- `quantitative`: giá trị, đơn vị và fact/source hints.
- `comparison`: operator như minimum/maximum/greater_than cùng supplier scope đầy đủ.
- `qualitative`: criterion/source requirement; không được suy ra từ marketing text.
- `risk`: risk fact, knowledge status và action đề xuất.

Mỗi predicate dùng metric/operator nằm trong allowlist server-side. Không parse hoặc execute biểu thức, SQL hay formula do LLM tạo.

### 4.3. Output mẫu

```json
{
  "decision": {
    "type": "ranked_recommendation",
    "preferred_supplier_id": "A",
    "summary": "Ưu tiên A theo tổng chi phí và thời gian giao; B có bảo hành dài hơn.",
    "supporting_claim_ids": ["cl-A-cost", "cl-A-lowest-cost", "cl-A-delivery", "cl-A-fastest", "cl-B-warranty"],
    "reason_codes": ["LOWER_TOTAL_COST", "SHORTER_DELIVERY"],
    "uncertainty_ids": ["unc-quality"]
  },
  "recommendation": {
    "top_n": 3,
    "ranked": [
      {
        "rank": 1,
        "supplier_id": "A",
        "supplier_name": "Vendor A",
        "rationale": "TCO 12.000 USD, thấp nhất trong scope; giao 5 ngày, nhanh nhất trong scope.",
        "rationale_claim_ids": ["cl-A-cost", "cl-A-lowest-cost", "cl-A-delivery", "cl-A-fastest"],
        "comparison_ids": ["cmp-cost", "cmp-delivery", "cmp-warranty"],
        "trade_off_ids": ["trade-warranty"],
        "risk_ids": ["risk-quality-gap"],
        "uncertainty_ids": ["unc-quality"],
        "evidence": []
      },
      {
        "rank": 2,
        "supplier_id": "B",
        "supplier_name": "Vendor B",
        "rationale": "TCO 14.500 USD và giao 7 ngày; bảo hành 24 tháng so với 12 tháng của A.",
        "rationale_claim_ids": ["cl-B-cost", "cl-B-delivery", "cl-B-warranty"],
        "comparison_ids": ["cmp-cost", "cmp-delivery", "cmp-warranty"],
        "trade_off_ids": ["trade-warranty"],
        "risk_ids": ["risk-quality-gap"],
        "uncertainty_ids": ["unc-quality"],
        "evidence": []
      }
    ],
    "shortfall": {
      "requested_count": 3,
      "available_count": 2,
      "returned_count": 2,
      "reason_code": "AVAILABLE_CANDIDATES_BELOW_REQUESTED_TOP_N"
    }
  },
  "claims": [
    {
      "claim_id": "cl-A-cost",
      "category": "quantitative",
      "supplier_ids": ["A"],
      "text": "TCO của A là 12.000 USD.",
      "predicate": {"operator": "equals", "metric": "tco", "value": "12000.00", "unit": "USD"},
      "source_hints": ["Goods total and shipping charge in Vendor A quotation"],
      "calculation_hints": ["sum_declared_tax_inclusive_components"]
    },
    {
      "claim_id": "cl-A-lowest-cost",
      "category": "comparison",
      "supplier_ids": ["A", "B"],
      "text": "A có TCO thấp nhất trong scope.",
      "predicate": {"operator": "minimum", "metric": "tco", "subject_supplier_id": "A", "tie_handling": "disclose"},
      "source_hints": ["Totals for every supplier in the comparison scope"],
      "calculation_hints": []
    },
    {
      "claim_id": "cl-A-delivery",
      "category": "quantitative",
      "supplier_ids": ["A"],
      "text": "A giao hàng trong 5 ngày lịch sau xác nhận đơn hàng.",
      "predicate": {"operator": "equals", "metric": "delivery_days", "value": "5", "unit": "calendar_day", "time_origin": "order_confirmation"},
      "source_hints": ["Vendor A delivery commitment"],
      "calculation_hints": []
    },
    {
      "claim_id": "cl-A-fastest",
      "category": "comparison",
      "supplier_ids": ["A", "B"],
      "text": "A có thời gian giao ngắn nhất trong scope.",
      "predicate": {"operator": "minimum", "metric": "delivery_days", "subject_supplier_id": "A", "tie_handling": "disclose"},
      "source_hints": ["Delivery commitments for every supplier in the comparison scope"],
      "calculation_hints": []
    },
    {
      "claim_id": "cl-B-cost",
      "category": "quantitative",
      "supplier_ids": ["B"],
      "text": "TCO của B là 14.500 USD.",
      "predicate": {"operator": "equals", "metric": "tco", "value": "14500.00", "unit": "USD"},
      "source_hints": ["Goods total and shipping charge in Vendor B quotation"],
      "calculation_hints": ["sum_declared_tax_inclusive_components"]
    },
    {
      "claim_id": "cl-B-delivery",
      "category": "quantitative",
      "supplier_ids": ["B"],
      "text": "B giao hàng trong 7 ngày lịch sau xác nhận đơn hàng.",
      "predicate": {"operator": "equals", "metric": "delivery_days", "value": "7", "unit": "calendar_day", "time_origin": "order_confirmation"},
      "source_hints": ["Vendor B delivery commitment"],
      "calculation_hints": []
    },
    {
      "claim_id": "cl-B-warranty",
      "category": "comparison",
      "supplier_ids": ["A", "B"],
      "text": "B bảo hành 24 tháng; A bảo hành 12 tháng.",
      "predicate": {"operator": "greater_than", "metric": "warranty_months", "subject_supplier_id": "B", "other_supplier_id": "A"},
      "source_hints": ["Warranty terms for A and B"],
      "calculation_hints": []
    }
  ],
  "comparisons": [
    {"comparison_id": "cmp-cost", "criterion": "tco", "supplier_ids": ["A", "B"], "claim_ids": ["cl-A-cost", "cl-B-cost", "cl-A-lowest-cost"], "coverage": "complete"},
    {"comparison_id": "cmp-delivery", "criterion": "delivery_days", "supplier_ids": ["A", "B"], "claim_ids": ["cl-A-delivery", "cl-B-delivery", "cl-A-fastest"], "coverage": "complete"},
    {"comparison_id": "cmp-warranty", "criterion": "warranty_months", "supplier_ids": ["A", "B"], "claim_ids": ["cl-B-warranty"], "coverage": "complete"}
  ],
  "trade_offs": [
    {"trade_off_id": "trade-warranty", "preferred_supplier_id": "A", "alternative_supplier_id": "B", "benefit_claim_ids": ["cl-A-lowest-cost", "cl-A-fastest"], "cost_claim_ids": ["cl-B-warranty"], "uncertainty_ids": ["unc-quality"], "text": "Chọn A ưu tiên chi phí và tốc độ; buyer cần cân nhắc lợi ích bảo hành của B."}
  ],
  "negotiation_points": [
    {"negotiation_id": "neg-A-warranty", "supplier_id": "A", "kind": "suggestion", "action": "Đề nghị A kéo dài bảo hành.", "basis_claim_ids": ["cl-B-warranty"], "expected_outcome": null}
  ],
  "risk_flags": [
    {"risk_id": "risk-quality-gap", "supplier_ids": ["A", "B"], "risk_type": "quality_information_gap", "knowledge_status": "unknown", "severity": "unknown", "claim_ids": [], "uncertainty_ids": ["unc-quality"], "suggested_action": "Không ưu tiên NCC nào dựa trên xếp hạng chất lượng chưa có dữ liệu."}
  ],
  "uncertainties": [
    {"uncertainty_id": "unc-quality", "supplier_ids": ["A", "B"], "description": "Chưa có xếp hạng chất lượng được xác minh.", "impact": "Không thể kết luận B có chất lượng cao hơn A.", "suggested_criticality": "noncritical", "proposed_action": "disclose_and_exclude_from_scoring"}
  ],
  "open_questions": [
    {"question_id": "question-quality", "supplier_ids": ["A", "B"], "uncertainty_ids": ["unc-quality"], "question": "Có đánh giá chất lượng độc lập để bổ sung không?", "proposed_owner": "buyer"}
  ],
  "assumptions": []
}
```

Ví dụ chủ ý không có claim “B chất lượng cao hơn A”. Nếu LLM sinh claim này mà không có criterion/source đủ điều kiện, Evaluation sẽ route `REPAIR_OUTPUT` hoặc `REQUEST_DATA`.

## 5. Evidence Node với ChromaDB

### 5.1. Trách nhiệm

Evidence Node nhận `rationale`, `claims` và server-provided source scope. Với từng claim, node tìm chunk nguyên gốc phù hợp từ ChromaDB, sau đó trả retrieval artifacts. Node không lấy quote text từ LangGraph state và không coi vector similarity là bằng chứng cuối cùng.

Chunk trong ChromaDB cần có tối thiểu:

| Metadata | Mục đích |
| --- | --- |
| `document_id`, `document_hash`, `source_kind` | Đúng file và đúng revision |
| `supplier_id`, `quote_id`, `item_id` khi có | Đúng đối tượng được claim nhắc tới |
| `page`, `block_id`, `table_id`, `row_id`, `cell_locator` | Citation đọc được và giữ ngữ cảnh bảng |
| `parent_chunk_id`, `chunk_hash` | Tải header/context/neighbor và kiểm toàn vẹn |
| `case/tenant access metadata` | Chỉ tìm nguồn ứng dụng cho phép |

Với bảng, index phải giữ headers, đơn vị, currency, conditions/footnotes và hàng/cột liên quan. Một ô số rời không đủ làm evidence.

### 5.2. Retrieval theo claim

1. Tách từng factual claim từ proposal; không query toàn bộ rationale rồi tái dùng một citation cho tất cả claims.
2. Lập query từ text claim, metric, supplier/quote/item, unit và conditions.
3. Server tạo filter/allowed source IDs theo case và source scope; LLM không truyền filter quyền.
4. Query Chroma cho candidate chunks; comparative claim phải tìm evidence cho toàn bộ suppliers trong scope.
5. Tải exact records theo ID, kèm parent/table header/neighbor khi candidate thiếu ngữ cảnh.
6. Giữ cả hit supporting và hit contradicting có liên quan.
7. Lưu chunk ID, exact stored excerpt, locator, hash và retrieval trace thành EvidenceArtifact.

Chroma Query dùng nearest-neighbor similarity; Get tải bản ghi theo ID, không qua similarity ranking. Query/Get có metadata filtering để giới hạn corpus. [Chroma Query and Get](https://docs.trychroma.com/docs/querying-collections/query-and-get), [Chroma Metadata Filtering](https://docs.trychroma.com/docs/querying-collections/metadata-filtering).

### 5.3. Các loại evidence

| Loại claim | Cách chứng minh |
| --- | --- |
| Direct | Chunk gốc chứa giá trị, unit và điều kiện phù hợp. |
| Derived | Chunks nguồn của các operands + replay phép tính thuộc allowlist. |
| Comparative | Evidence của toàn bộ supplier trong scope + phép so sánh deterministic + tie handling. |
| Human edit | Audit edit được xác thực + tham chiếu nguồn gốc để nhìn thấy before/after. |
| Unknown disclosure | Artifact evaluation chỉ rõ dữ liệu chưa xác minh; không biến “không tìm thấy” thành fact về NCC. |

Evidence có bốn trạng thái: `supported`, `contradicted`, `unresolved`, `not_found`. Retrieval score/distance chỉ hỗ trợ tìm kiếm/calibration; nó không phải xác suất claim đúng và không thể tự mở cổng approval.

### 5.4. EvidenceArtifact

```json
{
  "evidence_id": "ev-A-delivery",
  "recommendation_id": "rec-case-demo-1",
  "recommendation_version": 1,
  "claim_id": "cl-A-delivery",
  "evidence_kind": "direct_source",
  "support_status": "supported",
  "sources": [
    {
      "chunk_id": "chunk-A-delivery",
      "document_id": "doc-A",
      "document_hash": "demo-hash-A",
      "page": 2,
      "block_id": "delivery-terms",
      "table_id": null,
      "row_id": null,
      "cell_ids": [],
      "exact_excerpt": "Delivery: 5 calendar days after order confirmation.",
      "context_excerpt": "Delivery: 5 calendar days after order confirmation.",
      "source_kind": "quotation"
    }
  ],
  "verification": {
    "value_match": true,
    "unit_match": true,
    "scope_match": true,
    "condition_match": true,
    "source_revision_match": true
  },
  "retrieval_trace": {
    "query_id": "query-cl-A-delivery",
    "candidate_chunk_ids": ["chunk-A-delivery"],
    "distance": 0.12
  }
}
```

Exact excerpt phải là substring của stored chunk. Một model không được viết lại câu trích dẫn rồi gắn như evidence.

## 6. Năm tầng evaluation

### 6.1. Decision validation

Kiểm cấu trúc và nhất quán proposal:

- decision type phù hợp ranked list;
- supplier IDs thuộc candidate scope do application cấp;
- rank liên tục, unique; preferred supplier khớp rank 1;
- Top-N/shortfall hợp logic quy tắc runtime;
- claim, comparison, trade-off, risk, uncertainty references tồn tại và không trùng;
- tất cả assertion factual trong summary/rationale/risk/trade-off/negotiation/assumption đều có claim ID.

Output lỗi cấu trúc hoặc claim dư nhưng có đủ dữ liệu để sửa: `REPAIR_OUTPUT`. Supplier không thuộc candidate scope: `REPAIR_OUTPUT` nếu chỉ là lỗi output; `technical_failure` nếu scope/context không xác thực được.

### 6.2. Constraint validation

Kiểm feasibility của từng supplier so với hard/soft constraints runtime: scope/coverage, quantity/spec, budget, deadline, commercial conditions và unknown handling.

Mỗi constraint trả `pass | fail | unknown | not_applicable`. NCC vi phạm hard constraint không được rank. Fact bắt buộc unknown đi `REQUEST_DATA`. Soft constraint phải hiện trong trade-off; không được tự biến thành hard constraint.

Nếu output chọn NCC fail nhưng có candidate hợp lệ khác, route `REPAIR_OUTPUT`. Nếu không có candidate viable, trả `REPORT_NO_VIABLE_SUPPLIER`, không tạo ranking giả.

### 6.3. Evidence-grounding validation

Sau Evidence Node, verifier kiểm:

- mỗi factual claim hiển thị có source đúng supplier/item/revision/context;
- exact excerpt, row/header/cell context tồn tại;
- value, currency, UOM, time origin và conditions khớp predicate;
- derived calculations replay được bằng Decimal, operator/formula allowlist và rounding đã định;
- comparative claims có full supplier coverage và tie handling;
- counter-evidence không bị bỏ qua;
- unknown/critical uncertainty được tạo hoặc giữ lại kèm impact/action.

Claim optional không được support có thể loại bằng `REPAIR_OUTPUT`. Claim quyết định hoặc mandatory comparison không có nguồn đi `REQUEST_DATA`. Chroma timeout/index error là `RETRY_TRANSIENT` rồi `technical_failure`, không được chuyển thành business pass/fail.

### 6.4. Business-rule validation

Kiểm rules runtime về số candidate tối thiểu, mandatory comparisons, single-source/exception, authority và cách xử lý unavailable data.

Đây là tầng khác Constraint validation: Constraint kiểm NCC có đáp ứng yêu cầu hay không; Business-rule kiểm quy trình chọn recommendation có được phép không.

Fairness rule bắt buộc:

- fee/price thiếu không trở thành 0;
- lead time unknown không được coi là nhanh;
- quality/compliance unknown không được coi là tốt;
- criteria optional thiếu phải được xử lý cùng cách giữa các NCC;
- không re-normalize weights riêng cho từng NCC để NCC thiếu dữ liệu có lợi.

Hard rule fail chỉ route `REQUEST_EXCEPTION` khi rule runtime nói rõ có ngoại lệ và actor đúng authority. Buyer approval thông thường không tự bỏ qua blocker.

### 6.5. Recommendation quality evaluation

Chỉ chạy sau bốn tầng bắt buộc pass. Chấm utility bằng rubric anchored 0–4:

| Dimension | 0–1 | 3–4 |
| --- | --- | --- |
| Rationale clarity | Chung chung/mâu thuẫn | Specific, nhất quán với claims |
| Comparison completeness | Thiếu criterion/alternative material | Đủ scope và comparisons bắt buộc |
| Trade-off usefulness | Chỉ nêu NCC thắng | Nêu benefit/cost của lựa chọn |
| Uncertainty disclosure | Che unknown/blocker | Nêu impact, owner, next action |
| Actionability | Buyer không biết xử lý gì | Có quyết định/đàm phán/bổ sung rõ |

LLM judge có thể hỗ trợ clarity/usefulness, nhưng không có quyền override deterministic, evidence hoặc business-rule failure. Điểm trung bình không bù cho critical uncertainty bị che giấu.

## 7. Check catalog theo yêu cầu

| Check | Tầng chính | Pass khi | Fail route |
| --- | --- | --- | --- |
| No unsupported claim | Decision + Grounding | Toàn bộ factual assertions đã khai báo và supported | Repair claim dư; mandatory claim thiếu → data |
| No missing mandatory comparison | Business rule + Quality | Có đủ comparison bắt buộc và full scope | Repair khi facts đủ; thiếu fact → data |
| All numerical calculations reproducible | Grounding | Replay khớp operands, formula, unit, rounding | Output sai → repair; thiếu dependency/source → data |
| All recommendation claims backed by sources | Grounding | Direct/derived/comparative evidence graph đầy đủ | Repair hoặc data theo tính bắt buộc |
| Decision respects procurement policy | Constraint + Business rule | Hard rules pass hoặc exception hợp lệ | Exception/input/no viable |
| No supplier receives advantage from unavailable data | Business rule | Unknown không cải thiện rank/score | Repair hoặc input |
| Critical uncertainty explicitly disclosed | Constraint + Grounding + Quality | Disclosure có impact, owner, next action | Repair; critical missing fact → data |

## 8. Evaluation result, action và routing

### 8.1. Result contract

```json
{
  "evaluation_id": "eval-rec-case-demo-1-attempt-1",
  "recommendation_id": "rec-case-demo-1",
  "recommendation_version": 1,
  "attempt": 1,
  "overall_status": "repairable",
  "stage_results": [
    {"stage": "decision", "status": "pass", "issue_ids": []},
    {"stage": "constraint", "status": "pass", "issue_ids": []},
    {"stage": "evidence_grounding", "status": "fail", "issue_ids": ["issue-quality-claim"]},
    {"stage": "business_rule", "status": "not_run", "issue_ids": []},
    {"stage": "recommendation_quality", "status": "not_run", "issue_ids": []}
  ],
  "check_results": [
    {"check_id": "NO_UNSUPPORTED_CLAIM", "status": "fail", "issue_ids": ["issue-quality-claim"]},
    {"check_id": "NO_MISSING_MANDATORY_COMPARISON", "status": "not_run", "issue_ids": []},
    {"check_id": "ALL_NUMERICAL_CALCULATIONS_REPRODUCIBLE", "status": "pass", "issue_ids": []},
    {"check_id": "ALL_RECOMMENDATION_CLAIMS_BACKED_BY_SOURCES", "status": "fail", "issue_ids": ["issue-quality-claim"]},
    {"check_id": "DECISION_RESPECTS_PROCUREMENT_POLICY", "status": "not_run", "issue_ids": []},
    {"check_id": "NO_SUPPLIER_ADVANTAGE_FROM_UNAVAILABLE_DATA", "status": "not_run", "issue_ids": []},
    {"check_id": "CRITICAL_UNCERTAINTY_EXPLICITLY_DISCLOSED", "status": "not_run", "issue_ids": []}
  ],
  "issues": [
    {
      "issue_id": "issue-quality-claim",
      "stage": "evidence_grounding",
      "code": "UNSUPPORTED_OPTIONAL_CLAIM",
      "severity": "error",
      "claim_ids": ["claim-extra-quality"],
      "supplier_ids": ["B"],
      "action": "REPAIR_OUTPUT",
      "owner": "decision_llm"
    }
  ],
  "required_actions": [
    {"action_id": "act-repair-1", "type": "REPAIR_OUTPUT", "issue_ids": ["issue-quality-claim"], "route": "repair_decision_llm"}
  ],
  "quality": null
}
```

Stage/check status: `pass | fail | unknown | not_applicable | not_run`. Overall status: `ready_for_review | repairable | needs_input | exception_required | no_viable_supplier | technical_failure`.

### 8.2. Action catalog

| Action | Trigger | Route |
| --- | --- | --- |
| `CONTINUE` | Current stage pass | Stage kế tiếp |
| `REPAIR_OUTPUT` | Có lỗi output và dữ liệu đủ | Repair LLM → chạy lại toàn bộ evaluation |
| `RETRIEVE_MORE_EVIDENCE` | Thiếu table/header/parent context nhưng corpus khả dụng | Evidence Node, tối đa một expansion |
| `REQUEST_DATA` | Thiếu fact/source bắt buộc hoặc cần correction | Chờ nguồn upstream xử lý → nhận output LLM mới |
| `REQUEST_EXCEPTION` | Rule fail nhưng cho phép ngoại lệ | Chờ approver có authority → output LLM mới |
| `REPORT_NO_VIABLE_SUPPLIER` | Không có candidate đáp ứng | Chờ buyer xử lý/close |
| `RETRY_TRANSIENT` | Timeout/chroma/network tạm thời | Retry backoff có giới hạn |
| `ESCALATE_REPAIR_LIMIT` | Output/issue lặp không tiến triển | Chờ manual resolution |
| `PRESENT_FOR_REVIEW` | Mandatory checks pass và quality đạt | HITL-2 |
| `FINALIZE_APPROVAL` | Approve đúng version/authority | Approved → END |
| `FINALIZE_REJECTION` | Reject hợp lệ | Rejected → END |
| `CLOSE_CASE` | Buyer đóng case | Closed → END |

Ưu tiên route: integrity/authorization → technical/transient → missing data/exception/no viable → repairable output → warnings. Một warning không che blocker. Đề xuất mặc định tối đa 2 automatic repairs, 1 evidence expansion; retry dịch vụ và buyer revise dùng counters riêng.

## 9. Human feedback và HITL-2

### 9.1. Feedback contract

```json
{
  "feedback_id": "feedback-demo-1",
  "recommendation_id": "rec-case-demo-1",
  "recommendation_version": 1,
  "idempotency_key": "review-action-demo-1",
  "decision": "revise",
  "revision_type": "preference_change",
  "note": "Ưu tiên bảo hành khi cân nhắc A và B.",
  "target_ids": ["trade-warranty"],
  "requested_changes": {
    "explanation_change": null,
    "preference_change": {"ordered_metrics": ["warranty_months", "tco", "delivery_days"]},
    "data_corrections": []
  },
  "acknowledged_uncertainty_ids": ["unc-quality"]
}
```

Server lấy actor ID, roles, authority và submitted timestamp từ authenticated context; không nhận các field đó từ LLM hoặc request body.

### 9.2. Route feedback

| Feedback | Route |
| --- | --- |
| `approve` | Chỉ accept khi recommendation version là current, status ready-for-review, buyer đủ authority và đã acknowledge critical uncertainty bắt buộc. Lưu approval/audit atomically. |
| `reject` | Lưu lý do, version và audit; terminal Rejected. Không coi giá trị khác `revise` là approve. |
| `revise/explanation_change` | Repair Decision LLM; evidence/evaluation của version cũ không dùng cho output mới. |
| `revise/preference_change` | Chuyển yêu cầu cho owner của preferences; chờ output Decision LLM mới rồi restart evaluation. |
| `revise/data_correction` | Chuyển correction có before/after/source/reason cho owner dữ liệu; chờ output mới. |
| `revise/rule_change` | Chỉ authority tương ứng mới xử lý; chờ output mới. |
| `revise/mixed` | Tách change set; route theo thay đổi rộng nhất. |

Feedback state có `received`, `applied`, `awaiting_clarification`. “Đưa note vào prompt” không đồng nghĩa với feedback applied; output version mới phải qua toàn bộ evaluation.

Approval dùng compare-and-set trên `recommendation_id + recommendation_version + awaiting_review` và idempotency key. Cùng key/cùng payload trả kết quả cũ; cùng key/khác payload trả conflict. Điều này chặn stale approval và double-click.

## 10. Rủi ro kỹ thuật và giải pháp

| Rủi ro | Giải pháp |
| --- | --- |
| Vector hit tương tự nhưng sai số/supplier/revision | Typed value/unit/condition checks, source metadata, counter-evidence; không pass bằng distance. |
| Bảng mất header/unit/footnote | Fetch parent/header/neighbor; thiếu tiếp là unresolved. |
| Claim tự do ngoài danh sách claims | Assertion inventory + repair; final renderer chỉ dùng claims verified. |
| TCO xuất hiện như số đã tính, không có câu nguồn nguyên văn | Evidence graph gồm operand chunks + replay formula allowlist; không ép PDF phải ghi “TCO”. |
| “Lowest” chỉ chứng minh NCC thắng | Bắt full scope evidence và deterministic comparison; xử lý tie. |
| Unknown tạo lợi thế | Business-rule fairness check và typed unknown states. |
| Corpus Chroma thay đổi hoặc index chưa ready | Source filters/hashes, readiness checks; technical failure/retry, không fallback sang state. |
| Prompt injection trong quote chunk | Chunks chỉ là dữ liệu; rules/router/approval dùng server-authoritative config. |
| LLM judge cho điểm cao với evidence sai | Judge chỉ dùng ở quality layer, không override bốn gates trước. |
| Restart/resume hoặc approval trùng | Persistent state/checkpoint, idempotency, compare-and-set và audit event. |

Nếu dùng LangGraph cho HITL, interrupt cần checkpointer bền vững và thread ID; node có interrupt có thể chạy lại phần code trước interrupt khi resume, nên writes phải idempotent. [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

## 11. Thứ tự triển khai

1. Định nghĩa Pydantic contracts cho LLM output, runtime evaluation context, evidence artifact, evaluation result và feedback.
2. Viết fixtures/oracles ẩn danh: valid, unsupported numeric claim, missing evidence, wrong supplier/revision, no viable, unavailable-data advantage, stale approval.
3. Triển khai Decision và Constraint validators thuần, không gọi LLM/Chroma.
4. Xây Chroma ingestion metadata contract, adapter Query/Get và evidence retrieval per claim.
5. Triển khai grounding verifier, calculation replay và comparative full-scope checks.
6. Thêm Business-rule/fairness validator, quality rubric và deterministic action router.
7. Nối HITL-2, typed feedback, persistence, idempotency và audit.
8. Chạy acceptance matrix, đo latency/false-support/repair loop rồi mới tối ưu k, cache và concurrency.

Acceptance tối thiểu: không unsupported claim; không missing mandatory comparison; numerical calculations replay được; factual claims có source graph; decision tuân rules; missing data không làm NCC có lợi; critical uncertainty luôn được disclose; approve stale/duplicate bị từ chối; reject là terminal đúng nghĩa.