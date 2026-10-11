# Synchronize canonical procurement models with confirmed contracts

## TL;DR
> Summary: Align canonical Pydantic models with the confirmed domain, pipeline, and API contracts, using separate models whenever those layers have different shapes. Add exhaustive isolated model checks; leave runtime migration for its separately authorized follow-up.
> For whom: Backend developers, future pipeline/API implementers, and programs consuming serialized procurement contracts gain unambiguous, validated model boundaries.
> Deliverables:
> - Canonical domain records, component payloads, artifact envelopes, and API bodies with explicit exports.
> - Decimal-string and UTC serialization, field provenance, mandatory human confirmation, and revision references.
> - Isolated contract tests and an explicit legacy-consumer impact report in execution evidence.
> Effort: Large
> Risk: High - existing services directly import canonical names, and confirmed contract changes intentionally invalidate some of their payloads.

## Scope
### Affected user and ideal state
**Affected user:** Programmers currently encounter canonical models copied from legacy schemas or combining multiple layers; future consumers need exact contract names and wire shapes without importing application services. Buyers and managers benefit when those consumers migrate, but this assignment does not change their running workflow.

The ideal state for this assignment includes complete model-boundary coverage; runtime migration is explicitly outside its scope.

| Row | Statement | Reason |
|-----|-----------|--------|
| IS-1 | Every specified domain record can be instantiated independently with its documented identity, ownership, revision, state, and audit fields. | Storage consumers must not infer missing fields from unrelated response objects. |
| GAP-1 | PR, document, quotation, approval, PO, analysis, and job models lack fields or mix layers. | See `src/models/purchase_request.py:54`, `document.py:11`, `quotation/confirmation.py:40`, `approval.py:25`, `purchase_order.py:26`, `workflow.py:26`. |
| IS-2 | Pipeline and API examples validate and serialize with their own exact shapes; differing layers have distinct models. | Prevents storage-only fields and legacy proposal shapes leaking into public boundaries. |
| GAP-2 | Artifact, OCR, extraction, normalized quotation, decision, and response models disagree with the confirmed examples. | See `src/models/workflow.py:33`, `document.py:43`, `quotation/extraction.py:47`, `analysis/normalization.py:8`, `analysis/decision.py:190`. |
| IS-3 | Money, quantity, rates, and string-valued confidence are finite decimals serialized as strings; timestamps serialize in UTC. | Prevents numeric precision loss and ambiguous audit times. |
| GAP-3 | Quantity is explicitly serialized to float, many financial fields use float, and default timestamps are naive. | See `src/models/common.py:9`, `analysis/tco.py:12`, `purchase_order.py:43`, `quotation/confirmation.py:59`. |
| IS-4 | Human confirmation is mandatory, field confidence/provenance remain separate from confirmed revisions, missing normalized values remain null, and shipping unknowns remain null. | Maintains the confirmed human-review and provenance guarantees. |
| GAP-4 | Raw extraction permits `needs_confirmation=False`, normalized lines inherit raw extraction, and confirmed quotations include shipping/legacy OCR data. | See `src/models/quotation/extraction.py:68`, `analysis/normalization.py:8`, `quotation/confirmation.py:63`. |
| IS-5 | Every concrete canonical contract model is exercised, package imports remain resolvable, and migration incompatibilities are explicitly identified without editing protected consumers. | Makes the new model surface usable without falsely claiming runtime compatibility. |
| GAP-5 | Existing model tests import the legacy bridge, root test setup imports the application, and some runtime consumers already import canonical modules. | See `tests/test_models/test_procurement.py:6`, `tests/conftest.py:7`, `src/agents/nodes/decision_llm.py:15`, `src/services/procurement/workflow.py:29`. |

### Must have
- Source precedence is layer-specific: `specs/contracts/domain-and-storage.md` for domain/storage records; `pipeline.md` for component payloads/envelopes; `api.md` for public request/response bodies. The caller confirmed these documents despite their older DRAFT heading.
- Modify only canonical `src/models` files and new/updated model tests under `tests/test_models`. This plan file is the planning deliverable.
- Keep Pydantic 2, `extra="forbid"`, explicit public typing, and class docstrings. Canonical models must never import/inherit old models or import services/routes/agents (`src/models/README.md:32`, `:36`, `:44`).
- Concrete decision on collisions: `DecisionProposal` in `analysis/decision.py` becomes the six-field pipeline proposal. Rename the existing evaluator-shaped class to `LegacyDecisionProposal` within that file; retain its existing helper classes and `Recommendation` until consumer migration. `src/models/evaluation.py.DecisionProposal` remains the untouched legacy bridge class. Never combine these shapes or make the canonical name a union.
- Concrete naming policy: unsuffixed domain entity names follow domain/storage. Use `OCRDocumentRepresentation`/`OCRDocumentBlock` for pipeline OCR payloads, `ArtifactEnvelope[T]` for the pipeline envelope, and explicit `*Response` names for public response projections. Reuse the same class only when complete wire shapes match (the pipeline `ConfirmedQuotationRevision` wrapper and API confirmation response match).
- Domain record fields must be exactly the corresponding domain field lists. Optional domain fields marked `?` and semantically pending values are nullable; do not invent nested relationships absent from those lists.
- Preserve independently imported transitional extraction helpers (`RawExtraction`, `SourceReference`, `Surcharge`, `ExtractedPage`, `ExtractedQuotationItem`, `ExtractedQuotation`, `ExtractionStatus`, `ExtractionResult`, `BatchExtractionResult`) and noncontract PR/PO/decision helpers. Add new exact models alongside them. These helpers are not the new contract and must be explicitly classified in test inventory; no silent canonical alias to a legacy shape.
- Preserve `ConfirmedQuotation` as the existing transitional class; redefine `Quotation` as the domain identity, not its existing alias. Preserve importability of `DataNormalized` as an alias of the new `NormalizedQuotation`, documenting its payload incompatibility. Preserve current PR command/helper symbols because PR create/update HTTP bodies are not specified in these contract files; do not redesign undocumented API requests.
- Snapshot caller/user changes before implementation, never stage or overwrite unrelated hunks, and serialize changes to package `__init__.py` files in Task 9.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- No edits to `src/models/old/**`, `src/models/schemas.py`, `procurement.py`, `evaluation.py`, `pr.py`, `extracted_quotation.py`, `procurement_workflow.py`, application consumers, contract documents, config, requirements, Makefile, or existing non-model tests.
- No schema generation from runtime old schemas, broad `Any` payloads in specified structures, aliases accepting obsolete field names on new canonical records, speculative endpoints, ORM, database migration, confidence-policy engine, normalization/TCO calculations, HTTP handlers, or service-level state transitions.
- No validation requiring database lookups: tenant authorization, supplier membership in a stored snapshot, revision concurrency, uniqueness/idempotency, immutable persistence, and lifecycle transitions remain service responsibilities. Models encode references and local field invariants only.
- No automatic confidence-threshold override on confirmation requests, auto-confirm branch, shipping input in confirmation, float serializer for decimals, naive datetime default, or fallback from missing normalized values to source values.
- No full-repository formatting or `make check`: `Makefile:18` invokes a format target that changes out-of-scope files. Use the nonmutating checks below and report the scoped substitution.
- No claim of whole-backend compatibility or entirely green `ruff check src/models` when a protected baseline error remains.

### Boundary decisions and implementation details
These decisions fill details not fully prescribed by the prose; they are deliberate model-design choices, not additional claims about confirmed business behavior.

- `Quantity` uses finite `Decimal > 0`; monetary values use finite `Decimal >= 0`; rates/confidence strings use finite Decimal in `[0,1]`. Do not impose a currency-wide two-decimal precision limit absent from the contracts. Native Pydantic JSON serialization emits decimal strings. OCR `confidence` remains a bounded float because its specific pipeline example uses a JSON number (`pipeline.md:71`). Existing transitional float fields are not an excuse to use floats in new contract fields.
- Use `UTCDatetime = Annotated[AwareDatetime, AfterValidator(...astimezone(timezone.utc))]`; naive values fail, offset-aware values normalize. Persisted contract timestamps are required inputs except documented nullable completion timestamps; do not generate timestamps while deserializing persisted records. Dates stay dates. Pydantic's documented Decimal and aware-datetime behavior: https://pydantic.dev/docs/validation/latest/api/pydantic/standard_library_types/ .
- Use `str` IDs with `min_length=1`, not UUID-only parsing: contract examples also use `supplier-id`/`pr-id`. Positive version/revision/page/attempt numbers; nonnegative byte size/duration; progress `[0,100]`. Unknown keys fail. Default only genuinely nullable/pending values or empty output collections, never required commercial values.
- Keep `ContractModel` mutable so existing aggregate/helper use is not globally frozen. Use a separate `ImmutableContractModel` for confirmed revision content, original document metadata/content, and audit decisions. Freeze nested confirmed item models and use tuple-backed immutable collections that serialize as JSON arrays. Lifecycle records whose status changes (`QuotationRevision`, `Analysis`, jobs) remain replaceable records; storage immutability is outside this change. Explicitly test the immutable pipeline confirmation snapshot and its nested content; do not claim `frozen=True` protects arbitrary JSON dictionaries.
- For structures whose entries are not specified (`tradeoffs`, normalization `issues`, storage `*_json`), use `JsonValue`/`dict[str, JsonValue]` instead of inventing an evidence schema. Restrict public arbitrary JSON to explicitly specified `details` and error structures; all provenance fields use safe declared fields.
- `ExtractionDraft` consists of commercial fields matching confirmation (supplier_name, currency, vat_rate, vat_included, lead_time_days, warranty_months, payment_terms), each wrapped in `ExtractionField[T](value: T | None, confidence: Decimal | None, source: FieldSource | None)`, plus `items`. `ExtractionDraftItem` has `source_item_id` and wrapped product_name/product_code/unit/quantity/unit_price. Missing extracted values remain null; do not require a complete buyer payload at extraction time. The API extraction example is partial: absent additional wrappers default to None, and `exclude_unset=True` reproduces its exact subset. This does not add header totals or shipping.
- `FieldSource` contains required document_id, page_number, block_id and optional bounding_box/source_text, never filesystem paths. Existing `SourceReference` is a transitional internal helper; new public models must not reference it.
- `FieldValidationIssue` is the small pipeline/API shape: field_path, code, severity (`warning|blocking`), confidence nullable. Storage `ValidationIssue` separately has its IDs and `details_json`.
- `DecisionContext` contains only `tco_results`, `comparison_matrix`, `risk_flags`, `pr_constraints: PurchaseRequestInput`, and positive `top_n`. No raw OCR, evaluator payload, or proposal facts. Keep the input helper's existing field names where the prose does not specify them; change its budget to finite Decimal and remove its wall-clock deadline rejection so historical snapshots deserialize. Its constraints are a model-shape choice, not a new HTTP body.
- TCO/risk/comparison field detail is not fully specified (`pipeline.md:228`): retain the existing detailed structures, switch financial/rate numeric fields to Decimal, support missing values explicitly, constrain new canonical comparison criteria to `total_tco|lead_time_days|warranty_months`, and add `RiskAssessment(risk_flags)` and `SupplierComparison` (same typed structure as ComparisonMatrix). No new arithmetic, currency assumptions, or tax formula.
- For an incomplete API analysis response, represent the documented empty `comparison_matrix: {}` using `ComparisonMatrix` whose collections default empty and serialize unset fields with `exclude_unset=True` when reproducing that example. Completed matrices serialize their supplied typed contents. Do not require a nonempty comparison during `queued` state.

### Expected consumer impact (report; do not fix here)
Based on direct imports, the premise that all backend consumers use old schemas is not true in this checkout:

| Consumer reference | Expected consequence after alignment |
|---|---|
| `src/services/procurement/purchase_requests.py:14`, `:28`, `:47` | Old PR JSON and constructors contain quantity/creator_name and omit tenant/version/UOM/updated_at; canonical PurchaseRequest validation will reject them. |
| `src/services/procurement/purchase_orders.py:11`; `src/services/procurement/workflow.py:29`, `:508`, `:575` | Old PO creation/replay lacks approval/snapshot/revision references and sends removed display fields. |
| `src/services/quotation/repository.py:14`, `:50`, `:60`, `:177`; `src/services/quotation/intake.py:18`, `:139` | `Quotation` is now an identity, not a file-and-commercial snapshot; old source_path accesses and old QuotationItem line_total inputs are incompatible. |
| `src/agents/nodes/decision_llm.py:15`, `:47`, `:95` | LLM structured-output schema switches to the six-field proposal, while downstream evaluator/prompt code expects the old shape. This same-name collision is unavoidable under the required canonical naming. |
| `src/agents/nodes/normalize.py:7`; `src/agents/tools/calculate_tco.py:7`; `compare_suppliers.py:8`; `analyze_risks.py:11` | Normalization payload shape changes; decimal dumps and constrained comparison criteria may invalidate old calculations/presentation expectations. |
| `src/models/old/extracted_quotation.py:3`; `src/extraction/service.py:7`; `src/extraction/quotation_parser.py:6`; `src/extraction/pdf_extractor.py:11` | The nominally old extraction bridge imports canonical transitional helpers; keep those helper symbols and their old schemas intact in this assignment. |
| `tests/conftest.py:7`; `tests/test_infrastructure_logging.py:13` | Global test collection loads the application; isolated model checks must bypass root conftest. Keep PR command helper symbols importable. |

Whole-backend readiness is not a success criterion for this model-only assignment. Consumer migrations need a later authorized change; do not conceal failures by broadening models to accept both shapes.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD + pytest. Each implementation task adds its tests in the same logical commit; capture the failing contract assertion before the fix when practical.
- QA policy: every task has agent-executed scenarios. Tests use static local fixture data, never the app, disk repositories, providers, or network.
- Evidence: `<attemptDir>/task-<N>-<slug>.<ext>` — under ulw-loop, `<attemptDir>` is the `currentAttemptDir` from `omo-agent-toolkit ulw-loop status --json` (`.omo/evidence/ulw/<session>/<goalId>/a<attempt>`); outside ulw-loop use `.omo/evidence/`.
- Windows commands below run from `V:/P-109`; use `.venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models ... -q -p no:cacheprovider`. Do not edit `tests/conftest.py` to isolate tests. Test modules import canonical model modules only. All named new test files below are created by their task.
- At execution start capture `git status --short`, `git diff -- src/models tests/test_models`, and SHA-256 hashes of protected old/bridge files in evidence. Do not print `.env` or secrets. Recheck protected hashes at completion.
- Known lint baseline (observed 2026-10-05): `ruff check --no-cache src/models --output-format concise` returns 12 I001 import-order errors, 11 canonical and one protected `src/models/old/extracted_quotation.py:3`. Fix canonical diagnostics only. Run the required unfiltered command anyway and require its final diagnostics be empty or exactly the unchanged protected baseline; separately require canonical-only lint exit 0. This is an explicit scope limitation, not an all-green claim.
- Canonical-only lint: `.venv/Scripts/ruff.exe check src/models --extend-exclude src/models/old --extend-exclude src/models/schemas.py --extend-exclude src/models/procurement.py --extend-exclude src/models/evaluation.py --extend-exclude src/models/pr.py --extend-exclude src/models/extracted_quotation.py --extend-exclude src/models/procurement_workflow.py`.
- Type check explicit canonical files with `.venv/Scripts/python.exe -B -m mypy --follow-imports=silent --ignore-missing-imports src/models/common.py src/models/document.py src/models/purchase_request.py src/models/purchase_order.py src/models/approval.py src/models/workflow.py src/models/api.py src/models/quotation/extraction.py src/models/quotation/confirmation.py src/models/analysis/normalization.py src/models/analysis/tco.py src/models/analysis/risk.py src/models/analysis/comparison.py src/models/analysis/decision.py`. Capture baseline before changes for existing files; final canonical diagnostics must be resolved without editing protected modules. Installed environment has Pydantic 2.13.5 and mypy; do not add dependencies.

## Execution strategy
### Parallel execution waves
> Target 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks to maximize parallelism.

Wave 1 (shared prerequisite):
- Task 1: shared decimal/time primitives and immutable snapshot base. One task because these shared definitions must land atomically; artificial subdivision would create shared-file conflicts.

Wave 2 (after Wave 1):
- Task 2: document storage and OCR payloads; depends [1].
- Task 3: PR domain and snapshot constraints; depends [1].
- Task 4: quotation identity, extraction, confirmation; depends [1].
- Task 5: Buyer/Manager record and command models; depends [1].
- Task 6: PO domain/projection models; depends [1].
- Task 7: normalization, deterministic outputs, proposal; depends [1]. Use a type-checking/forward import for PurchaseRequestInput if needed while Task 3 runs; Task 3 preserves its symbol.

Wave 3 (integration prerequisite):
- Task 8: storage workflow records, pipeline envelopes, and API projections; depends [2,3,4,5,6,7]. This owns the one new API module and must be atomic to avoid conflicting projections.

Wave 4 (final implementation verification):
- Task 9: exports, exhaustive contract inventory, isolation/baseline audits; depends [8].

Critical path: Task 1 -> Task 4 -> Task 8 -> Task 9

### Dependency matrix
| Task | Depends on | Blocks | Can parallelize with |
|------|------------|--------|----------------------|
| 1 | none | 2,3,4,5,6,7 | none |
| 2 | 1 | 8 | 3,4,5,6,7 |
| 3 | 1 | 8 | 2,4,5,6,7 |
| 4 | 1 | 8 | 2,3,5,6,7 |
| 5 | 1 | 8 | 2,3,4,6,7 |
| 6 | 1 | 8 | 2,3,4,5,7 |
| 7 | 1 | 8 | 2,3,4,5,6 |
| 8 | 2,3,4,5,6,7 | 9 | none |
| 9 | 8 | F1,F2,F3,F4 | none |

## Todos
> Implementation + Test = ONE task. Never separate.
> Every task MUST have: References + Acceptance Criteria + QA Scenarios + Commit.

- [ ] 1. Establish decimal-string and UTC primitives with snapshot immutability

  What to do: Update `common.py` per boundary decisions: remove Quantity's float PlainSerializer; add finite amount/rate/string-confidence aliases, `UTCDatetime`, `ImmutableContractModel`, reusable nonempty ID alias. Keep numeric OCR ConfidenceScore separately named. Keep ContractModel's existing extra-forbid behavior. Add `test_contract_common.py`; use small local test-only models for scalar tests. Do not touch package exports yet.
  Must NOT do: Globally freeze ContractModel, quantize/round values, upgrade dependencies, change old schemas, or add a serializer recursively rewriting arbitrary dictionaries.
  Closes: GAP-3, GAP-4

  Parallelization: Can parallel: NO | Wave 1 | Blocks: [2,3,4,5,6,7] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern: `src/models/common.py:9-21` - current primitive definitions/base config.
  - API/Type: `specs/contracts/api.md:10`, `:187`; `pipeline.md:196` - UTC and decimal boundaries.
  - Test: `tests/test_models/test_procurement.py:88` - ValidationError test style, but import canonical models in new tests.
  - External: https://pydantic.dev/docs/validation/latest/api/pydantic/standard_library_types/ - Decimal JSON and AwareDatetime behavior.

  Acceptance criteria (agent-executable only):
  - [ ] `.venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_common.py -q -p no:cacheprovider` exits 0.
  - [ ] Assertions prove `Decimal('0.125')` quantity remains `'0.125'`, money `'15000000.00'` stays a string, NaN/infinity fail, naive timestamp fails, `2026-10-05T08:30:00+07:00` dumps as `2026-10-05T01:30:00Z`, and frozen model assignment raises `frozen_instance`.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: precise decimal and UTC round trip
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_common.py -k round_trip -q -p no:cacheprovider
    Expected: exit 0; Decimal values round-trip without floats; offset normalizes to UTC.
    Evidence: <attemptDir>/task-1-primitives.txt
  Scenario: invalid primitives and frozen mutation
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_common.py -k invalid -q -p no:cacheprovider
    Expected: exit 0; tests assert Pydantic finite_number, timezone_aware, extra_forbidden, frozen_instance errors.
    Evidence: <attemptDir>/task-1-primitives-error.txt
  ```

  Commit: YES | Message: `refactor(models): define precise canonical value primitives` | Files: [src/models/common.py, tests/test_models/test_contract_common.py]

- [ ] 2. Separate document records from OCR component payloads

  What to do: In `document.py`, add `Document` with exactly id/tenant_id/pr_id/filename/media_type/byte_size/content_hash/file_path/status/created_by/created_at. Change `UploadedDocument` to exactly document_id/filename/file_path/content_hash. Make `DocumentRepresentation` the storage record id/document_id/engine/engine_version/created_at, and `DocumentBlock` the storage record id/representation_id/page_number/block_id/kind/text/bounding_box_json/confidence. Add `OCRDocumentBlock(block_id,kind,text,bounding_box,confidence)` and `OCRDocumentRepresentation(document_id,pages,engine,engine_version)`; update `DocumentPage(page_number,blocks)` to use OCRDocumentBlock. Use UTC timestamps, bounded numeric OCR confidence, four-coordinate bbox validation, immutable document/OCR snapshots; keep storage path present internally. Add `test_contract_document.py`.
  Must NOT do: Merge storage IDs into OCR payloads, remove internal file_path from domain serialization, invent a document classifier, or create storage/upload code.
  Closes: GAP-1, GAP-2, GAP-3

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [8] | Blocked by: [1]

  References:
  - Pattern: `src/models/document.py:11-51` - current four mixed classes.
  - API/Type: `specs/contracts/domain-and-storage.md:25-57`; `pipeline.md:41-79` - both exact shapes.
  - Test: `tests/test_models/test_contract_common.py` from Task 1 - scalar validations.
  - External: https://pydantic.dev/docs/validation/latest/api/pydantic/standard_library_types/ - tuple/list JSON serialization.

  Acceptance criteria:
  - [ ] `.venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_document.py -q -p no:cacheprovider` exits 0.
  - [ ] Exact `model_fields` sets match each storage/pipeline list; OCR example validates without representation_id/created_at or block-level page_number.

  QA scenarios:
  ```
  Scenario: independent storage and OCR shapes
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_document.py -k shapes -q -p no:cacheprovider
    Expected: exit 0; all six models plus DocumentPage instantiate; OCR dump equals supplied example; Document retains internal file_path.
    Evidence: <attemptDir>/task-2-document.txt
  Scenario: invalid OCR and mixed layer fields
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_document.py -k invalid -q -p no:cacheprovider
    Expected: exit 0; wrong engine/kind reject with literal_error, page 0 with greater_than_equal, extra storage IDs in OCR with extra_forbidden, malformed bbox fails length constraint.
    Evidence: <attemptDir>/task-2-document-error.txt
  ```

  Commit: YES | Message: `refactor(models): separate document storage and OCR payloads` | Files: [src/models/document.py, tests/test_models/test_contract_document.py]

- [ ] 3. Align PurchaseRequest and replayable PR constraints

  What to do: Replace PurchaseRequest fields with exact domain list: id, tenant_id, code, creator_id, category, requested_quantity, requested_uom, target_currency, estimated_budget, delivery_due_date, status, version, created_at, updated_at. Remove creator_name, quantity, quotation_count, rejection_reason, po_id from this canonical record. Keep existing PRStatus literals. Use Quantity/finite amount/UTC types. Update PurchaseRequestInput budget to Decimal and permit historical deadline replay; preserve existing helper names/commands and aliases because no new create/update HTTP contract is specified. Add `test_contract_purchase_request.py` including explicit old-payload rejection.
  Must NOT do: Edit repositories, infer tenant IDs, add old-name aliases on PurchaseRequest, change unspecified command bodies, or require a future date on a persisted snapshot.
  Closes: GAP-1, GAP-3, GAP-5

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [8] | Blocked by: [1]

  References:
  - Pattern: `src/models/purchase_request.py:20-94` - snapshot, entity, existing helper exports.
  - API/Type: `specs/contracts/domain-and-storage.md:5-23`; `pipeline.md:238`, `:250` - PR record/constraints input.
  - Test: `tests/test_models/test_procurement.py:72` - historic bridge test to preserve unmodified.
  - External: https://pydantic.dev/docs/validation/latest/api/pydantic/standard_library_types/ - date versus datetime.

  Acceptance criteria:
  - [ ] `.venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_purchase_request.py -q -p no:cacheprovider` exits 0.
  - [ ] Domain exact field set asserted; fractional requested_quantity round-trips as string; historical PurchaseRequestInput deadline validates; PR helper symbols remain importable.

  QA scenarios:
  ```
  Scenario: complete PR and historical constraints
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_purchase_request.py -k round_trip -q -p no:cacheprovider
    Expected: exit 0; historical date 2020-01-01 accepted; requested_quantity '2.5' and budget serialized as strings.
    Evidence: <attemptDir>/task-3-pr.txt
  Scenario: legacy record shape and invalid revision
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_purchase_request.py -k invalid -q -p no:cacheprovider
    Expected: exit 0; quantity/creator_name payload produces extra_forbidden and missing errors; version 0 rejected.
    Evidence: <attemptDir>/task-3-pr-error.txt
  ```

  Commit: YES | Message: `refactor(models): align purchase request domain records` | Files: [src/models/purchase_request.py, tests/test_models/test_contract_purchase_request.py]

- [ ] 4. Model quotation identity, provenance, full confirmation, and revision boundaries

  What to do:
  - In `quotation/extraction.py`, preserve transitional helpers and add `QuotationExtraction` with exact fields from domain lines 99-106; use `human_confirmation_required: Literal[True]`, Decimal applied_confidence_threshold, and extracted/validated/failed status. Add storage `ExtractedField` and `ValidationIssue` with exact domain fields/IDs. raw_value/parsed_value use JsonValue; raw_value is never derived from a correction.
  - Add safe `FieldSource`, generic `ExtractionField[T]`, `ExtractionDraftItem`, `ExtractionDraft`, `FieldValidationIssue`, and `ValidatedExtraction(schema_valid,human_confirmation_required,issues)` per boundary decisions. Every extraction requires human confirmation even with confidence 1.00; a schema_valid=False payload is representable and does not throw away issues. Do not synthesize issues based on a hardcoded threshold in a model.
  - In `quotation/confirmation.py`, replace Quotation alias with exact domain `Quotation` identity and all five statuses. Add exact domain `QuotationRevision` and `QuotationItemRevision` (quantity_decimal/unit_price_decimal names; IDs and created_at; no nested items on the domain row).
  - Redefine API `QuotationItem` as source_item_id/product_name/product_code/unit/quantity/unit_price; no required line_total. Redefine `QuotationConfirmation` as supplier_name/currency/vat_rate/vat_included/lead_time_days/warranty_months/payment_terms/items/review_note; full commercial fields required, review_note nullable. source_item_id is required/nonempty for current confirm requests. Monetary zero is permitted; quantity must be positive. No shipping or supplier_id allowed.
  - Add immutable `ConfirmedQuotationRevisionData` with revision_id/revision_no/status Literal['confirmed']/supplier_id + full commercial fields/items/review_note/confirmed_by/confirmed_at; add immutable `ConfirmedQuotationRevision(quotation_id,revision)` wrapper. Optional product_code may be empty but the full confirmation key must be present. Preserve old ConfirmedQuotation class as explicitly transitional, including its existing legacy fields; do not use it from new contract models.
  - Add `test_contract_quotation.py`. Keep current `__init__` imports resolvable; exports are finalized in Task 9.
  Must NOT do: Apply corrections to extracted raw values, accept confirmation supplier_id/threshold/shipping overrides, auto-confirm based on confidence, remove old extraction bridge helpers, or add per-quotation threshold configuration.
  Closes: GAP-1, GAP-2, GAP-3, GAP-4

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [8] | Blocked by: [1]

  References:
  - Pattern: `src/models/quotation/extraction.py:18-144`; `quotation/confirmation.py:10-75` - keep transitional helpers separated.
  - API/Type: `specs/contracts/domain-and-storage.md:59-130`; `pipeline.md:84-196`; `api.md:67-191` - storage/draft/confirmation fields and confidence behavior.
  - Test: `tests/test_models/test_procurement.py:12-71` - old compatibility tests remain on bridge; new tests use exact canonical types.
  - External: https://pydantic.dev/docs/validation/latest/concepts/models/ - generic models and frozen model configuration.

  Acceptance criteria:
  - [ ] `.venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_quotation.py -q -p no:cacheprovider` exits 0.
  - [ ] All new storage and component models are instantiated; API confirm request and response fixtures match exact key sets; Decimal fractional quantity survives; missing extraction values stay None.
  - [ ] Confirmed wrapper/items reject assignment and tuple mutation; machine draft remains a distinct object with its original values after confirmed values differ.

  QA scenarios:
  ```
  Scenario: extraction provenance and full confirmed revision
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_quotation.py -k round_trip -q -p no:cacheprovider
    Expected: exit 0; provenance includes document/page/block; quantity '10.5', unit_price '15000000.00', confidence '0.74' remain strings; confidence '1.00' still requires human confirmation.
    Evidence: <attemptDir>/task-4-quotation.txt
  Scenario: client overrides and missing confirmation fields
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_quotation.py -k invalid -q -p no:cacheprovider
    Expected: exit 0; supplier_id/shipping_fee/confidence_threshold on confirmation produce extra_forbidden; missing currency/source_item_id produces missing; human_confirmation_required=False produces literal_error; confirmed mutation produces frozen_instance.
    Evidence: <attemptDir>/task-4-quotation-error.txt
  ```

  Commit: YES | Message: `refactor(models): separate quotation drafts identities and confirmed revisions` | Files: [src/models/quotation/extraction.py, src/models/quotation/confirmation.py, tests/test_models/test_contract_quotation.py]

- [ ] 5. Separate approval domain records from commands and pipeline confirmation

  What to do: In `approval.py`, keep BuyerRecommendationSubmission and ManagerDecisionRequest exact API body fields. Require non-whitespace note for Buyer revise, selected_supplier_id for Manager approve, and non-whitespace reason for Manager revise/reject. Reuse these local validators for immutable domain records without inheriting extra API-only fields. Change BuyerRecommendationConfirmation to exact domain id/tenant_id/pr_id/analysis_id/analysis_revision/decision_proposal_artifact_id/action/note/buyer_id/idempotency_key/created_at. Change ApprovalDecision to exact domain id/tenant_id/pr_id/analysis_id/analysis_revision/buyer_confirmation_id/decision/selected_supplier_id/reason/actor_id/idempotency_key/created_at. Add separately named `BuyerRecommendationConfirmationPayload` for pipeline analysis_id/analysis_revision/decision_proposal_id/buyer_id/action/note/created_at (timestamp key chosen consistently because pipeline prose does not name it). Manager pipeline can reuse ApprovalDecision: no divergent field shape is prescribed there. Add `test_contract_approval.py`.
  Must NOT do: Mix submitted_at with domain created_at, enforce database state/role checks, or accept Buyer approve/create-PO actions.
  Closes: GAP-1, GAP-2, GAP-3, GAP-4

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [8] | Blocked by: [1]

  References:
  - Pattern: `src/models/approval.py:11-66` - existing validators and missing identity fields.
  - API/Type: `specs/contracts/domain-and-storage.md:165-195`; `pipeline.md:275-298`; `api.md:243-305` - per-layer review contracts.
  - Test: `tests/test_models/test_contract_common.py` from Task 1 - UTC/frozen primitives.
  - External: https://pydantic.dev/docs/validation/latest/concepts/validators/ - after-model validation.

  Acceptance criteria:
  - [ ] `.venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_approval.py -q -p no:cacheprovider` exits 0.
  - [ ] Exact fields, submit/revise/approve/reject branches, non-whitespace requirements, UTC dumps, and immutable domain records are asserted.

  QA scenarios:
  ```
  Scenario: complete Buyer and Manager records
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_approval.py -k round_trip -q -p no:cacheprovider
    Expected: exit 0; domain IDs and idempotency keys remain present; API commands contain no actor/tenant fields supplied by the body.
    Evidence: <attemptDir>/task-5-approval.txt
  Scenario: unsupported or incomplete decisions
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_approval.py -k invalid -q -p no:cacheprovider
    Expected: exit 0; Buyer approve fails literal_error; whitespace revise note raises 'note is required when Buyer requests revision'; missing selected supplier raises 'selected_supplier_id is required when approving'; revise/reject without reason raises 'reason is required when revising or rejecting'.
    Evidence: <attemptDir>/task-5-approval-error.txt
  ```

  Commit: YES | Message: `refactor(models): distinguish approval records and command payloads` | Files: [src/models/approval.py, tests/test_models/test_contract_approval.py]

- [ ] 6. Align PurchaseOrder with approved snapshot references

  What to do: Replace PurchaseOrder fields with exact domain id/tenant_id/code/pr_id/approval_decision_id/analysis_id/snapshot_hash/supplier_id/quotation_revision_id/subtotal/shipping_amount/tax_amount/total_amount/currency/status/approver_id/approved_at/created_at. Keep draft/cancelled status. Monetary values are finite Decimals; subtotal/tax/total required, shipping_amount nullable default None; no zero substitution or model-side calculation. Preserve PurchaseOrderItem as a transitional standalone helper with decimal quantity/amount serialization; no undocumented nested items field on the canonical PO domain record. Public PO projection is added in Task 8. Add `test_contract_purchase_order.py`.
  Must NOT do: Copy amounts from DecisionProposal, retain removed display fields in the canonical entity, calculate shipping, or edit issuance service.
  Closes: GAP-1, GAP-3, GAP-4

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [8] | Blocked by: [1]

  References:
  - Pattern: `src/models/purchase_order.py:16-55` - current PO/helper fields.
  - API/Type: `specs/contracts/domain-and-storage.md:197-213`; `api.md:307-329` - different entity and response fields.
  - Test: `tests/test_models/test_contract_common.py` from Task 1.
  - External: https://pydantic.dev/docs/validation/latest/api/pydantic/standard_library_types/ - Decimal serialization.

  Acceptance criteria:
  - [ ] `.venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_purchase_order.py -q -p no:cacheprovider` exits 0.
  - [ ] Domain exact field set includes immutable calculation references, null shipping stays null, and all supplied amounts dump as strings.

  QA scenarios:
  ```
  Scenario: approved snapshot and unknown shipping
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_purchase_order.py -k round_trip -q -p no:cacheprovider
    Expected: exit 0; subtotal '100000.00', tax '10000.00', total '110000.00', shipping null preserved.
    Evidence: <attemptDir>/task-6-po.txt
  Scenario: missing provenance and invalid amounts
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_purchase_order.py -k invalid -q -p no:cacheprovider
    Expected: exit 0; missing approval_decision_id or quotation_revision_id raises missing; negative total rejected; old supplier_name/items extras rejected.
    Evidence: <attemptDir>/task-6-po-error.txt
  ```

  Commit: YES | Message: `refactor(models): anchor purchase orders to approved snapshots` | Files: [src/models/purchase_order.py, tests/test_models/test_contract_purchase_order.py]

- [ ] 7. Align normalized and analysis payloads and resolve DecisionProposal collision

  What to do:
  - Replace NormalizedLine inheritance with independent ContractModel fields source_quantity/source_uom/source_unit_price/source_currency/normalized_quantity/normalized_uom/normalized_unit_price/normalized_currency/rule_id. Normalized fields and rule_id are nullable when mapping is missing; source fields are required. Replace NormalizedQuotation with quotation_revision_id/rule_version/status (`normalized|needs_mapping`)/items/issues. For normalized status require all normalized fields and rule_id; for needs_mapping permit partial nulls, never fill source values. Keep DataNormalized import alias with the new semantics.
  - In tco.py retain current detailed TCOItem/TCOResult shape where contract prose is silent; replace float quantity/amount/rate operands and outputs with appropriate finite decimals. Preserve status/missing_fields validators, and make unknown amounts nullable instead of fabricated zero; only fields representing known neutral modifiers may retain explicitly justified zeros, with tests. No new calculations.
  - In comparison.py keep ComparisonCell/ComparisonMatrix, use finite Decimal or textual/null values (integer duration accepted and encoded appropriately; no monetary float); decimal means/deviations; constrain criteria/matrix keys to the three documented metrics. Add SupplierComparison with identical comparison fields. Keep default empty comparison valid for queued API snapshots.
  - In risk.py preserve RiskFlag and add RiskAssessment(risk_flags). Existing optional transitional source is not included in any new public projection; Task 8 uses a safe response projection if a source is emitted.
  - In decision.py rename the current evaluator-shaped class LegacyDecisionProposal; add canonical DecisionProposal(status,preferred_supplier_id,ranked_supplier_ids,rationale,tradeoffs,input_artifact_ids). Preferred supplier may be null for needs_input; require it and membership in ranked_supplier_ids when proposed. Distinct ranked IDs; no 'approved' status. Use JsonValue tradeoffs entries because the spec supplies no entry schema. Add DecisionContext per boundary decisions. Keep old helper classes and Recommendation, but canonical context/proposal must not reference them.
  - Add `test_contract_analysis.py` with normalization, TCO, matrix, risk, context, and both proposal shape checks. Avoid editing analysis/__init__.py until Task 9; its existing imports remain resolvable.
  Must NOT do: Inherit extraction data in normalized payloads, require raw OCR in decision context, invent evaluator/grounding steps, calculate TCO, or edit agent consumers to make old tests pass.
  Closes: GAP-2, GAP-3, GAP-4, GAP-5

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [8] | Blocked by: [1]

  References:
  - Pattern: `src/models/analysis/normalization.py:8-26`, `tco.py:8-40`, `comparison.py:7-24`, `risk.py:9-19`, `decision.py:190-231`.
  - API/Type: `specs/contracts/pipeline.md:198-273` - exact normalized/proposal shapes and deterministic tools' bounded responsibilities.
  - Test: `tests/test_models/test_procurement.py:39`, `:139` - existing legacy normalization/TCO behavior remains in old bridge tests.
  - External: https://pydantic.dev/docs/validation/latest/concepts/validators/ - cross-field validation without service lookups.

  Acceptance criteria:
  - [ ] `.venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_analysis.py -q -p no:cacheprovider` exits 0.
  - [ ] NormalizedQuotation validates the exact pipeline example without supplier_id/raw extraction fields; missing mapping stays null; proposal has exactly six fields and rejects old evaluator shape.
  - [ ] Empty matrix and populated three-criterion matrix both validate; financial operands/outputs serialize as strings; context contains exactly its five specified inputs.

  QA scenarios:
  ```
  Scenario: normalized analysis and compact proposal
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_analysis.py -k round_trip -q -p no:cacheprovider
    Expected: exit 0; source quantity '2' remains distinct from normalized '20'; needs_mapping nulls stay null; six-field proposal round-trips; context rejects raw data extras.
    Evidence: <attemptDir>/task-7-analysis.txt
  Scenario: invalid normalization and evaluator-shaped proposal
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_analysis.py -k invalid -q -p no:cacheprovider
    Expected: exit 0; normalized-with-null fails value_error; calculated TCO without total preserves existing validation error; preferred supplier outside ranked IDs fails value_error; old decision/recommendation/claims keys fail extra_forbidden; approved proposal fails literal_error.
    Evidence: <attemptDir>/task-7-analysis-error.txt
  ```

  Commit: YES | Message: `refactor(models): align analysis artifacts and canonical proposal` | Files: [src/models/analysis/normalization.py, src/models/analysis/tco.py, src/models/analysis/comparison.py, src/models/analysis/risk.py, src/models/analysis/decision.py, tests/test_models/test_contract_analysis.py]

- [ ] 8. Separate workflow storage, artifact envelopes, and complete API projections

  What to do:
  - In workflow.py make `Analysis` exact domain id/tenant_id/pr_id/revision_no/snapshot_hash/status/recommendation_id/created_by/created_at/completed_at; remove nested inputs. Add analysis_id to AnalysisInput. Make AnalysisArtifact exact id/analysis_id/artifact_type/schema_version/producer_version/payload_json/input_hash/created_at, using domain artifact literals.
  - Add generic `ArtifactEnvelope[T]` with exact pipeline artifact_id/artifact_type/schema_version/tenant_id/pr_id/input_artifact_ids/input_hash/producer/producer_version/created_at/payload; artifact_type is a nonempty string since the only exact example is normalized_quotation and other type strings are unspecified. Do not equate these strings with domain artifact enums. Tests instantiate envelopes with NormalizedQuotation and DecisionProposal and assert typed payload preservation.
  - Make WorkflowJob exact domain id/tenant_id/pr_id/job_type/status/current_step/progress/resource_id/error_json/idempotency_key/input_hash/created_at/updated_at. Make WorkflowJobEvent exact id/job_id/node/status/attempt/error_json/created_at. Define reusable literals for all ten documented steps, both job types, and five statuses. Restrict event node to documented steps.
  - Make AnalysisResult the complete API shape analysis_id/pr_id/analysis_revision/snapshot_hash/status/quotation_revision_ids/tco_results/risk_flags/comparison_matrix/decision_proposal/created_at/completed_at. Use a safe `RiskFlagResponse` projection (supplier_id/risk_type/severity/message/detail/source: FieldSource|None) rather than exposing transitional SourceReference paths. Define this projection in analysis/risk.py only if coordinated with Task 7 completion; Task 8 owns that follow-on change.
  - Create `src/models/api.py` containing `ErrorDetail(code,message,details,correlation_id)`, `ErrorEnvelope(error)`, `DocumentUploadResponse(document_id,filename,content_hash,job_id,status Literal['queued'])`, `WorkflowJobResponse(job_id,job_type,status,current_step,progress,resource_id,error: ErrorDetail|None,created_at,updated_at)`, `QuotationReviewResponse(quotation_id,status,human_confirmation_required Literal[True],confidence_threshold,draft_revision_no,extraction,validation_issues)` for the documented unconfirmed response, `AnalysisAcceptedResponse(analysis_id,analysis_revision,snapshot_hash,job_id,status Literal['queued'])`, `BuyerRecommendationSubmissionResponse(confirmation_id,analysis_id,analysis_revision,status Literal['pending_manager_approval'],submitted_by,submitted_at)`, `ManagerDecisionResponse(decision_id,status Literal['approved'],purchase_order_id)`, and `PurchaseOrderResponse(id,code,status,pr_id,analysis_id,snapshot_hash,quotation_revision_id,supplier_id,subtotal,shipping_amount,tax_amount,total_amount,currency)`.
  - Re-export matching existing request and resource response classes from api.py: QuotationConfirmation, ConfirmedQuotationRevision, BuyerRecommendationSubmission, ManagerDecisionRequest, AnalysisResult. No second implementation of identical confirmation response shape. QuotationReviewResponse covers unconfirmed draft documented at api.md:73; confirmed response uses ConfirmedQuotationRevision. No speculative response bodies for revise/reject are added.
  - Add `test_contract_workflow.py` and `test_contract_api.py`. Tests copy all concrete examples with 'a | b' placeholders replaced by one actual permitted value and 'ISO-8601 UTC' replaced by fixed timestamps. Include exact public key-set assertions and recursive path/provider/prompt absence assertions.
  Must NOT do: Put pipeline producer/input_artifact_ids on storage AnalysisArtifact, expose file_path/document_path/source_path, import routes, implement endpoints, or turn incomplete analysis {} into a required finished matrix.
  Closes: GAP-1, GAP-2, GAP-3, GAP-4, GAP-5

  Parallelization: Can parallel: NO | Wave 3 | Blocks: [9] | Blocked by: [2,3,4,5,6,7]

  References:
  - Pattern: `src/models/workflow.py:13-101` - existing lifecycle names/incorrect mixed envelopes.
  - API/Type: `specs/contracts/domain-and-storage.md:132-150`, `:215-238`; `pipeline.md:21-36`; `api.md:12-23`, `:39-62`, `:73-110`, `:155-184`, `:208-236`, `:266-304`, `:311-329`.
  - Test: Task 2/4/5/6/7 model fixtures and `tests/test_models/test_contract_common.py`.
  - External: https://pydantic.dev/docs/validation/latest/concepts/models/ - typed generic envelope behavior.

  Acceptance criteria:
  - [ ] `.venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_workflow.py tests/test_models/test_contract_api.py -q -p no:cacheprovider` exits 0.
  - [ ] All listed models instantiate and serialize; storage field sets differ intentionally from API/envelope field sets; all API fixture keys match documented bodies and use UTC strings/Decimal strings.
  - [ ] Public provenance cannot accept local paths, all job/analysis statuses and steps are covered, pending response comparison {} remains valid, and error correlation_id round-trips.

  QA scenarios:
  ```
  Scenario: domain envelope and API example parity
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_workflow.py tests/test_models/test_contract_api.py -k round_trip -q -p no:cacheprovider
    Expected: exit 0; every documented request/response example and both envelope payload examples validate; no public filesystem fields serialize.
    Evidence: <attemptDir>/task-8-boundaries.txt
  Scenario: cross-layer names and public path injection
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_workflow.py tests/test_models/test_contract_api.py -k invalid -q -p no:cacheprovider
    Expected: exit 0; job progress 101 fails less_than_equal; classifier current_step fails literal_error; domain job_id instead of id fails extra_forbidden/missing; source.document_path fails extra_forbidden; public response tenant/internal fields fail extra_forbidden.
    Evidence: <attemptDir>/task-8-boundaries-error.txt
  ```

  Commit: YES | Message: `refactor(models): separate workflow records and API projections` | Files: [src/models/workflow.py, src/models/api.py, src/models/analysis/risk.py, tests/test_models/test_contract_workflow.py, tests/test_models/test_contract_api.py]

- [ ] 9. Publish explicit exports and prove full contract coverage and scope

  What to do: Update `src/models/__init__.py`, `analysis/__init__.py`, `quotation/__init__.py` with explicit canonical exports and intentionally retained transitional symbols; format imports only in permitted canonical files. Add `test_contract_inventory.py` and test fixtures/helper under tests/test_models as needed. Discover concrete model classes by importing canonical modules only, filtering classes defined in those modules, excluding ContractModel/ImmutableContractModel and generic origins, and deduplicating aliases. Maintain an explicit registry mapping every discovered class either to a canonical fixture or to a named transitional classification; no newly introduced class may fall through. Every canonical fixture must validate, `model_dump(mode='json')`, `model_dump_json`, and revalidate; generic ExtractionField and ArtifactEnvelope require all actually used typed specializations. Transitional symbols require import smoke tests, not new business contract guarantees. Assert canonical model annotations do not point to transitional types except the expressly retained unspecific PR constraint helper and TCO/risk/comparison structures adapted above. Assert no canonical runtime imports of old/bridges/services/routes/agents using AST import inspection. Add subprocess import test for all canonical modules and all six unchanged bridges. Preserve existing legacy model tests and run them isolated too. Run full required lint/type checks and capture protected hashes and expected legacy consumer impact.
  Must NOT do: Make test inventory depend solely on __all__, suppress/skip missing fixtures, delete existing tests, import the full application in model tests, fix protected lint errors, or commit someone else's changes.
  Closes: GAP-1, GAP-2, GAP-3, GAP-4, GAP-5

  Parallelization: Can parallel: NO | Wave 4 | Blocks: [F1,F2,F3,F4] | Blocked by: [8]

  References:
  - Pattern: `src/models/__init__.py:3-17`, `analysis/__init__.py:3-19`, `quotation/__init__.py:3-13` - exports.
  - API/Type: entire confirmed three contract files, following layer precedence in this plan; `src/models/README.md:32-44` - import boundary/class documentation.
  - Test: `tests/test_models/test_procurement.py:6`; `tests/conftest.py:7` - retain legacy test and isolate parent application fixture.
  - External: https://pydantic.dev/docs/validation/latest/concepts/serialization/ - model dump and round-trip API.

  Acceptance criteria:
  - [ ] `.venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models -q -p no:cacheprovider` exits 0, includes all new canonical tests and unchanged legacy test_procurement.py, and does not load `src.main`.
  - [ ] Canonical-only lint command and explicit mypy command from Verification strategy exit 0; `.venv/Scripts/ruff.exe check src/models` is run and either passes or reports only the unchanged forbidden baseline described above.
  - [ ] `.venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_inventory.py -q -p no:cacheprovider` exits 0; coverage registry has no missing/unclassified concrete canonical classes; all bridge imports resolve without changing their sources.
  - [ ] Hash comparison shows protected files untouched by this assignment; `git diff --check -- src/models tests/test_models` exits 0; executor reports changed canonical consumers as future migration work, not regressions repaired here.

  QA scenarios:
  ```
  Scenario: full model inventory and import isolation
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models -q -p no:cacheprovider
    Expected: exit 0; every registered canonical model validates and JSON-round-trips; no src.main/services/routes/agents loaded by isolated canonical import subprocess.
    Evidence: <attemptDir>/task-9-inventory.txt
  Scenario: exhaustive registry detects drift and boundary violations
    Tool: powershell
    Steps: .venv/Scripts/python.exe -B -m pytest --confcutdir=tests/test_models tests/test_models/test_contract_inventory.py -k invalid -q -p no:cacheprovider
    Expected: exit 0; in-memory test-only unregistered class and forbidden import snippet are detected by audit helpers; unknown canonical model key raises extra_forbidden; fixture omission yields an explicit missing-fixture assertion. Tests do not mutate source files.
    Evidence: <attemptDir>/task-9-inventory-error.txt
  ```

  Commit: YES | Message: `test(models): enforce canonical contract coverage and import boundaries` | Files: [src/models/__init__.py, src/models/analysis/__init__.py, src/models/quotation/__init__.py, tests/test_models/test_contract_inventory.py, tests/test_models/contract_fixtures.py, permitted canonical import-formatting hunks]

## Final verification wave (MANDATORY - after all implementation tasks)
> Runs in PARALLEL. ALL must APPROVE. Surface results to the caller and wait for an explicit "okay" before declaring complete.
- [ ] F1. Plan compliance audit - every task done, every acceptance criterion met; required unfiltered lint outcome truthfully includes any protected baseline exception.
- [ ] F2. Code quality review - canonical diagnostics clean, idioms match, no dead code newly introduced; retained transitional helpers explicitly classified; no out-of-scope edits.
- [ ] F3. Real manual QA - every QA scenario executed with evidence captured; for this model surface, direct programmatic construction/serialization and invalid-input scenarios are the real interface, no browser or server required.
- [ ] F4. Ideal-state fidelity - delivered behavior checked against every IS row 1:1; a shortfall becomes new task rows, never a note; nothing Must-NOT-Have introduced. Runtime migrations remain outside the defined ideal state.

## Commit strategy
- One logical change per commit. Conventional Commits (`<type>(<scope>): <subject>` body + footer).
- Atomic: every commit imports successfully and passes its targeted model tests on its own. Cross-layer consumer behavior changes are the explicit scope tradeoff, not a claim that legacy application tests pass.
- No "WIP" / "fix typo squash later" commits on the final branch - clean up before merge.
- Reference the plan file path in the final commit footer: `Plan: .omo/plans/sync-contract-models.md`.
- Stage explicit owned paths/hunks; never `git add .`. No push/deploy. If the executor is not authorized to commit in its session, prepare the logical diff and report pending commit rather than silently creating commits.

## Success criteria
| IS | Delivering task(s) | Proving QA scenario | Evidence |
|----|--------------------|---------------------|----------|
| IS-1 | 2,3,4,5,6,8,9 | independent storage and OCR shapes; complete PR and historical constraints; extraction provenance and full confirmed revision; complete Buyer and Manager records; approved snapshot and unknown shipping; domain envelope and API example parity | <attemptDir>/task-2-document.txt; task-3-pr.txt; task-4-quotation.txt; task-5-approval.txt; task-6-po.txt; task-8-boundaries.txt |
| IS-2 | 2,4,5,7,8,9 | domain envelope and API example parity; cross-layer names and public path injection; normalized analysis and compact proposal | <attemptDir>/task-8-boundaries.txt; task-8-boundaries-error.txt; task-7-analysis.txt |
| IS-3 | 1,2,3,4,5,6,7,8,9 | precise decimal and UTC round trip; full model inventory and import isolation | <attemptDir>/task-1-primitives.txt; task-9-inventory.txt |
| IS-4 | 1,4,5,6,7,8 | extraction provenance and full confirmed revision; client overrides and missing confirmation fields; approved snapshot and unknown shipping; normalized analysis and compact proposal | <attemptDir>/task-4-quotation.txt; task-4-quotation-error.txt; task-6-po.txt; task-7-analysis.txt |
| IS-5 | 3,7,8,9 | full model inventory and import isolation; exhaustive registry detects drift and boundary violations | <attemptDir>/task-9-inventory.txt; task-9-inventory-error.txt; task-9-checks.txt (lint/type/hash/consumer-impact report) |
- Every IS row above has a delivering task and a proving scenario; all QA scenarios pass with captured evidence; F1-F4 approved; commit history clean. Protected baseline lint failures remain explicitly disclosed and unchanged; canonical checks must pass.
