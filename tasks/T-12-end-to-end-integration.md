# T-12 — Nối FE, BE, Agent và PO

Status: **In Review**

Nguồn yêu cầu: [end-to-end integration plan](../docs/end-to-end-integration-plan.md), được người dùng yêu cầu triển khai. Nhánh: `feature/connect_fe_be`.

- [x] Nối shared PR/quotation, supplier ID, financial inputs, audit và snapshot.
- [x] Inject persistent Chroma/EvaluationStore và trusted context; chạy graph trên dữ liệu đã confirm.
- [x] FE analysis/review, Manager feedback, finalize PO duy nhất và restart reconcile.
- [x] Agent PDF intake, corrections, explicit HITL resume và phục hồi pending sau restart.
- [x] API integration, browser happy path với provider giả và benchmark evaluation.
- [ ] Smoke extraction/decision bằng Groq hoặc Qwen thật: chưa có key/endpoint.
- [ ] Editor/command owner cho data/preference/rule revisions ngoài happy path.

Hướng dẫn và giới hạn: [runbook](../docs/end-to-end-runbook.md). Kết quả: [integration report](../docs/end-to-end-integration-results.md).
