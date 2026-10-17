"""Trust-separated contracts for the workflow after Decision LLM (§11.1)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Id = Annotated[str, Field(min_length=1)]
Number = Annotated[Decimal, Field(allow_inf_nan=False, max_digits=28)]
Metric = Literal["tco", "price", "fee", "quantity", "delivery_days", "warranty_months", "quality", "compliance"]
Status = Literal["pass", "fail", "unknown", "not_applicable", "not_run"]
Stage = Literal["decision", "constraint", "evidence_grounding", "business_rule", "recommendation_quality"]
ActionType = Literal[
    "CONTINUE",
    "REPAIR_OUTPUT",
    "RETRIEVE_MORE_EVIDENCE",
    "REQUEST_DATA",
    "REQUEST_EXCEPTION",
    "REPORT_NO_VIABLE_SUPPLIER",
    "RETRY_TRANSIENT",
    "ESCALATE_REPAIR_LIMIT",
    "PRESENT_FOR_REVIEW",
    "FINALIZE_APPROVAL",
    "FINALIZE_REJECTION",
    "CLOSE_CASE",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class QuantitativePredicate(Contract):
    operator: Literal["equals"]
    metric: Metric
    value: Number
    unit: Id
    time_origin: str | None = None
    conditions: list[str] = Field(default_factory=list)
    item_id: str | None = None
    quote_id: str | None = None


class ComparisonPredicate(Contract):
    operator: Literal["minimum", "maximum", "greater_than", "less_than"]
    metric: Metric
    subject_supplier_id: Id
    other_supplier_id: str | None = None
    tie_handling: Literal["disclose", "reject"] = "disclose"


class QualitativePredicate(Contract):
    operator: Literal["meets_criterion"]
    metric: Literal["quality", "compliance"]
    criterion: Id
    source_requirement: Literal["certificate", "independent_assessment", "human_edit"]
    value: bool


class ClaimBase(Contract):
    claim_id: Id
    supplier_ids: list[Id] = Field(min_length=1)
    text: Id
    source_hints: list[str] = Field(default_factory=list)
    calculation_hints: list[str] = Field(default_factory=list)


class QuantitativeClaim(ClaimBase):
    category: Literal["quantitative"]
    predicate: QuantitativePredicate


class ComparisonClaim(ClaimBase):
    category: Literal["comparison"]
    predicate: ComparisonPredicate


class QualitativeClaim(ClaimBase):
    category: Literal["qualitative"]
    predicate: QualitativePredicate


class RiskClaim(ClaimBase):
    category: Literal["risk"]
    predicate: QualitativePredicate
    knowledge_status: Literal["known", "unknown"]
    suggested_action: Id


Claim = Annotated[QuantitativeClaim | ComparisonClaim | QualitativeClaim | RiskClaim, Field(discriminator="category")]


class Decision(Contract):
    type: Literal["ranked_recommendation", "no_viable_supplier", "insufficient_candidates", "needs_input"]
    preferred_supplier_id: str | None
    summary: str
    supporting_claim_ids: list[str]
    reason_codes: list[str]
    uncertainty_ids: list[str]


class RankedItem(Contract):
    rank: int = Field(ge=1)
    supplier_id: Id
    supplier_name: str = ""
    rationale: str
    rationale_claim_ids: list[str]
    comparison_ids: list[str]
    trade_off_ids: list[str]
    risk_ids: list[str]
    uncertainty_ids: list[str]
    evidence: list[object] = Field(max_length=0)


class Shortfall(Contract):
    requested_count: int = Field(ge=1)
    available_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    reason_code: Literal["AVAILABLE_CANDIDATES_BELOW_REQUESTED_TOP_N"]


class Ranking(Contract):
    top_n: int = Field(ge=1)
    ranked: list[RankedItem]
    shortfall: Shortfall | None = None


class Comparison(Contract):
    comparison_id: Id
    criterion: Metric
    supplier_ids: list[Id]
    claim_ids: list[Id]
    coverage: Literal["complete", "incomplete"]


class TradeOff(Contract):
    trade_off_id: Id
    preferred_supplier_id: Id
    alternative_supplier_id: Id
    benefit_claim_ids: list[Id]
    cost_claim_ids: list[Id]
    uncertainty_ids: list[Id]
    text: str


class Negotiation(Contract):
    negotiation_id: Id
    supplier_id: Id
    kind: Literal["suggestion"]
    action: Id
    basis_claim_ids: list[Id]
    expected_outcome: None = None


class RiskFlag(Contract):
    risk_id: Id
    supplier_ids: list[Id]
    risk_type: Id
    knowledge_status: Literal["known", "unknown"]
    severity: Literal["low", "medium", "high", "critical", "unknown"]
    claim_ids: list[Id]
    uncertainty_ids: list[Id]
    suggested_action: Id


class Uncertainty(Contract):
    uncertainty_id: Id
    supplier_ids: list[Id]
    description: Id
    impact: Id
    suggested_criticality: Literal["critical", "noncritical"]
    proposed_action: Id
    proposed_owner: str = "buyer"


class OpenQuestion(Contract):
    question_id: Id
    supplier_ids: list[Id]
    uncertainty_ids: list[Id]
    question: Id
    proposed_owner: Id


class Assumption(Contract):
    assumption_id: Id
    text: Id
    claim_ids: list[Id]
    uncertainty_ids: list[Id]


class DecisionProposal(Contract):
    decision: Decision
    recommendation: Ranking
    claims: list[Claim]
    comparisons: list[Comparison]
    trade_offs: list[TradeOff]
    negotiation_points: list[Negotiation]
    risk_flags: list[RiskFlag]
    uncertainties: list[Uncertainty]
    open_questions: list[OpenQuestion]
    assumptions: list[Assumption]


class SourceScope(Contract):
    tenant_id: Id
    case_id: Id
    document_hashes: dict[str, str]
    source_kinds: list[str] = Field(
        default_factory=lambda: ["quotation", "certificate", "independent_assessment", "human_edit"]
    )


class Fact(Contract):
    supplier_id: Id
    metric: Metric
    value: Number | bool | None
    unit: str
    time_origin: str | None = None
    conditions: list[str] = Field(default_factory=list)
    item_id: str | None = None
    quote_id: str | None = None
    criterion: str | None = None

    @model_validator(mode="after")
    def metric_value_type(self) -> Fact:
        if self.value is not None:
            if self.metric in {"quality", "compliance"} and not isinstance(self.value, bool):
                raise ValueError("Qualitative facts require a boolean criterion verdict")
            if self.metric not in {"quality", "compliance"} and isinstance(self.value, bool):
                raise ValueError("Numeric metrics cannot use boolean values")
        return self


class Constraint(Contract):
    constraint_id: Id
    metric: Metric
    operator: Literal["lte", "gte", "equals"]
    value: Number | bool
    unit: str
    hard: bool = True
    supplier_ids: list[str] = Field(default_factory=list)


class Rule(Contract):
    rule_id: Id
    status: Literal["pass", "fail", "unknown", "not_applicable"]
    exception_allowed: bool = False
    exception_authority: str | None = None
    exception_granted_by: str | None = None
    exception_authorized: bool = False


class Calculation(Contract):
    """Server-defined operands, never an expression supplied by a model."""

    supplier_id: Id
    metric: Metric
    formula: Literal["sum_declared_tax_inclusive_components"]
    operand_chunk_ids: list[Id] = Field(min_length=1)
    unit: Id
    quantum: Number = Decimal("0.01")


class RuntimeEvaluationContext(Contract):
    case_id: Id
    recommendation_id: Id
    recommendation_version: int = Field(ge=1)
    candidate_ids: list[Id] = Field(min_length=1)
    source_scope: SourceScope
    top_n: int = Field(default=3, ge=1)
    facts: list[Fact] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    mandatory_comparisons: list[Metric] = Field(default_factory=list)
    formula_allowlist: list[Literal["sum_declared_tax_inclusive_components"]] = Field(default_factory=list)
    calculations: list[Calculation] = Field(default_factory=list)
    minimum_candidates: int = Field(default=2, ge=1)
    critical_uncertainty_ids: list[str] = Field(default_factory=list)
    material_alternative_ids: list[str] = Field(default_factory=list)
    optional_metrics: list[Metric] = Field(default_factory=list)
    authorized_edit_ids: list[str] = Field(default_factory=list)
    approval_role: str = "buyer"
    rule_change_role: str = "policy_admin"
    quality_minimum: int = Field(default=3, ge=0, le=4)

    @model_validator(mode="after")
    def valid_scope(self) -> RuntimeEvaluationContext:
        if self.source_scope.case_id != self.case_id or len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("Invalid application candidate/source scope")
        keys = [(f.supplier_id, f.metric) for f in self.facts]
        if len(keys) != len(set(keys)) or any(f.supplier_id not in self.candidate_ids for f in self.facts):
            raise ValueError("Duplicate or out-of-scope runtime facts")
        if any(c.quantum <= 0 for c in self.calculations):
            raise ValueError("Rounding quantum must be positive")
        if any(c.quantum.normalize().as_tuple().digits != (1,) for c in self.calculations):
            raise ValueError("Rounding quantum must be a power of ten")
        return self


class SourceFact(Fact):
    """Source span bindings produced by ingestion, checked against exact stored text."""

    value_text: Id
    metric_text: Id
    unit_text: str


class Chunk(Contract):
    chunk_id: Id
    text: Id
    tenant_id: Id
    case_id: Id
    document_id: Id
    document_hash: Id
    chunk_hash: Id
    source_kind: Id
    supplier_id: Id
    # TXT and authenticated edit blocks have a locator without a PDF page.
    page: int | None = Field(default=None, ge=1)
    block_id: Id
    quote_id: str | None = None
    item_id: str | None = None
    table_id: str | None = None
    row_id: str | None = None
    cell_locator: str | None = None
    parent_chunk_id: str | None = None
    context_chunk_ids: list[str] = Field(default_factory=list)
    context_complete: bool = True
    facts: list[SourceFact] = Field(default_factory=list)
    authenticated_edit_id: str | None = None
    original_chunk_id: str | None = None


class EvidenceSource(Contract):
    chunk: Chunk
    exact_excerpt: str
    context_excerpt: str


class RetrievalTrace(Contract):
    query_id: str
    candidate_chunk_ids: list[str] = Field(default_factory=list)
    distances: list[float] = Field(default_factory=list)
    expansion_count: int = Field(default=0, ge=0, le=1)


class EvidenceArtifact(Contract):
    evidence_id: Id
    recommendation_id: Id
    recommendation_version: int = Field(ge=1)
    claim_id: Id
    evidence_kind: Literal["direct_source", "derived", "comparative", "human_edit", "unknown_disclosure"]
    support_status: Literal["supported", "contradicted", "unresolved", "not_found"] = "unresolved"
    sources: list[EvidenceSource] = Field(default_factory=list)
    verification: dict[str, bool] = Field(default_factory=dict)
    retrieval_trace: RetrievalTrace
    tied_supplier_ids: list[str] = Field(default_factory=list)


class Issue(Contract):
    issue_id: Id
    stage: Stage
    code: Id
    severity: Literal["error", "warning"] = "error"
    claim_ids: list[str] = Field(default_factory=list)
    supplier_ids: list[str] = Field(default_factory=list)
    action: ActionType
    owner: str


class StageResult(Contract):
    stage: Stage
    status: Status
    issue_ids: list[str] = Field(default_factory=list)


class CheckResult(Contract):
    check_id: str
    status: Status
    issue_ids: list[str] = Field(default_factory=list)


class ConstraintResult(Contract):
    constraint_id: str
    supplier_id: str
    status: Status


class Action(Contract):
    action_id: str
    type: ActionType
    issue_ids: list[str] = Field(default_factory=list)
    route: str


class Quality(Contract):
    rationale_clarity: int = Field(ge=0, le=4)
    comparison_completeness: int = Field(ge=0, le=4)
    trade_off_usefulness: int = Field(ge=0, le=4)
    uncertainty_disclosure: int = Field(ge=0, le=4)
    actionability: int = Field(ge=0, le=4)


class EvaluationResult(Contract):
    evaluation_id: str
    recommendation_id: str
    recommendation_version: int
    attempt: int
    overall_status: Literal[
        "ready_for_review", "repairable", "needs_input", "exception_required", "no_viable_supplier", "technical_failure"
    ]
    stage_results: list[StageResult]
    check_results: list[CheckResult]
    issues: list[Issue]
    required_actions: list[Action]
    constraint_results: list[ConstraintResult] = Field(default_factory=list)
    evidence: list[EvidenceArtifact] = Field(default_factory=list)
    quality: Quality | None = None
    latency_ms: float = 0


class DataCorrection(Contract):
    target_id: Id
    before: str
    after: str
    source_id: Id
    reason: Id


class RequestedChanges(Contract):
    explanation_change: str | None = None
    preference_change: dict[str, list[Metric]] | None = None
    data_corrections: list[DataCorrection] = Field(default_factory=list)
    rule_change: str | None = None


class Feedback(Contract):
    feedback_id: Id
    recommendation_id: Id
    recommendation_version: int = Field(ge=1)
    idempotency_key: Id
    decision: Literal["approve", "reject", "revise", "close"]
    revision_type: (
        Literal["explanation_change", "preference_change", "data_correction", "rule_change", "mixed"] | None
    ) = None
    note: str = ""
    target_ids: list[str] = Field(default_factory=list)
    requested_changes: RequestedChanges = Field(default_factory=RequestedChanges)
    acknowledged_uncertainty_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def revision_matches_changes(self) -> Feedback:
        changes = self.requested_changes
        kinds = {
            k
            for k, v in {
                "explanation_change": changes.explanation_change,
                "preference_change": changes.preference_change,
                "data_correction": changes.data_corrections,
                "rule_change": changes.rule_change,
            }.items()
            if v
        }
        if self.decision == "revise":
            if not kinds or self.revision_type != (next(iter(kinds)) if len(kinds) == 1 else "mixed"):
                raise ValueError("Revision type must match the complete change set")
        elif kinds or self.revision_type is not None:
            raise ValueError("Only revise accepts changes")
        if self.decision in {"reject", "close"} and not self.note.strip():
            raise ValueError("A reason is required")
        return self


class Actor(Contract):
    """Obtained from authentication middleware; never deserialize from feedback."""

    actor_id: Id
    tenant_id: Id
    roles: list[str]
    case_ids: list[str]


class FeedbackReceipt(Contract):
    feedback_id: str
    recommendation_id: str
    recommendation_version: int
    state: Literal["received", "applied", "awaiting_clarification"]
    workflow_status: Literal["approved", "rejected", "closed", "awaiting_input", "awaiting_repair"]
    route: str


class AnalysisRunResponse(Contract):
    case_id: str
    status: Literal[
        "awaiting_review", "repairable", "needs_input", "exception_required", "no_viable_supplier", "technical_failure"
    ]
    recommendation_id: str | None = None
    recommendation_version: int | None = None
    evaluation: EvaluationResult | None = None
