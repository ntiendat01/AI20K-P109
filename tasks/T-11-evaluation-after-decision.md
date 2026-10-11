# T-11 — Evaluation sau Decision LLM

Status: **In Review**

Nguồn yêu cầu: [spec evaluation-after-decision-llm, mục 11](../docs/specs/evaluation-after-decision-llm.md).
Nhánh thực hiện theo yêu cầu: `feature/evaluation1`.

- [x] 1. Pydantic contracts, runtime trust boundary.
- [x] 2. Anonymous fixtures và independent expected oracles.
- [x] 3. Pure Decision/Constraint validators.
- [x] 4. Chroma ingestion metadata, scoped Query/Get, per-claim retrieval.
- [x] 5. Grounding, Decimal replay, comparison coverage/ties/counter-evidence.
- [x] 6. Business/fairness, anchored quality rubric, action router.
- [x] 7. Graph/API integration, durable HITL-2, typed feedback, CAS/idempotency/audit.
- [x] 8. Acceptance matrix, local Chroma integration, offline latency/false-support/repair-loop measurement.

Chi tiết vận hành, giới hạn verifier và kết quả: [implementation guide](../docs/evaluation-implementation.md), [benchmark](../docs/evaluation-acceptance-results.json).

Không tạo runtime policy/auth từ LLM; application phải inject source scope/context và authenticated actor. Không sửa pipeline extraction/normalization ngoài formatting do `make check`. Không thay đổi formula của tools TCO/comparison.
