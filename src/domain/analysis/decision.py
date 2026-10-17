"""Schemas for the Decision LLM structured proposal presented to Buyer HITL."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from src.domain.common import ContractModel

Id = Annotated[str, Field(min_length=1)]
Number = Annotated[Decimal, Field(allow_inf_nan=False, max_digits=28)]
Metric = Literal["tco", "price", "fee", "quantity", "delivery_days", "warranty_months", "quality", "compliance"]


class QuantitativePredicate(ContractModel):
    """State a numeric fact claimed by the recommendation."""

    operator: Literal["equals"]
    metric: Metric
    value: Number
    unit: Id
    time_origin: str | None = None
    conditions: list[str] = Field(default_factory=list)
    item_id: str | None = None
    quote_id: str | None = None


class ComparisonPredicate(ContractModel):
    """State a deterministic comparison between supplier values."""

    operator: Literal["minimum", "maximum", "greater_than", "less_than"]
    metric: Metric
    subject_supplier_id: Id
    other_supplier_id: str | None = None
    tie_handling: Literal["disclose", "reject"] = "disclose"


class QualitativePredicate(ContractModel):
    """State whether a supplier meets a named qualitative criterion."""

    operator: Literal["meets_criterion"]
    metric: Literal["quality", "compliance"]
    criterion: Id
    source_requirement: Literal["certificate", "independent_assessment", "human_edit"]
    value: bool


class ClaimBase(ContractModel):
    """Define identity, scope, and text shared by proposal claims."""

    claim_id: Id
    supplier_ids: list[Id] = Field(min_length=1)
    text: Id
    source_hints: list[str] = Field(default_factory=list)
    calculation_hints: list[str] = Field(default_factory=list)


class QuantitativeClaim(ClaimBase):
    """Describe a numeric claim grounded in a quantitative predicate."""

    category: Literal["quantitative"]
    predicate: QuantitativePredicate


class ComparisonClaim(ClaimBase):
    """Describe a cross-supplier claim grounded in a comparison predicate."""

    category: Literal["comparison"]
    predicate: ComparisonPredicate


class QualitativeClaim(ClaimBase):
    """Describe a quality or compliance claim."""

    category: Literal["qualitative"]
    predicate: QualitativePredicate


class RiskClaim(ClaimBase):
    """Describe a known or unknown risk and a suggested action."""

    category: Literal["risk"]
    predicate: QualitativePredicate
    knowledge_status: Literal["known", "unknown"]
    suggested_action: Id


Claim = Annotated[QuantitativeClaim | ComparisonClaim | QualitativeClaim | RiskClaim, Field(discriminator="category")]


class Decision(ContractModel):
    """Summarize the preferred supplier or explain why no decision is possible."""

    type: Literal["ranked_recommendation", "no_viable_supplier", "insufficient_candidates", "needs_input"]
    preferred_supplier_id: str | None
    summary: str
    supporting_claim_ids: list[str]
    reason_codes: list[str]
    uncertainty_ids: list[str]


class RankedItem(ContractModel):
    """Represent one supplier position in the proposed ranking."""

    rank: int = Field(ge=1)
    supplier_id: Id
    supplier_name: str = ""
    rationale: str
    rationale_claim_ids: list[str]
    comparison_ids: list[str]
    trade_off_ids: list[str]
    risk_ids: list[str]
    uncertainty_ids: list[str]
    evidence: list[object] = Field(default_factory=list, max_length=0)


class Shortfall(ContractModel):
    """Explain why fewer suppliers were ranked than the requested top N."""

    requested_count: int = Field(ge=1)
    available_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    reason_code: Literal["AVAILABLE_CANDIDATES_BELOW_REQUESTED_TOP_N"]


class Ranking(ContractModel):
    """Carry the ordered supplier recommendation and optional shortfall."""

    top_n: int = Field(ge=1)
    ranked: list[RankedItem]
    shortfall: Shortfall | None = None


class Comparison(ContractModel):
    """Link one comparison criterion to suppliers and supporting claims."""

    comparison_id: Id
    criterion: Metric
    supplier_ids: list[Id]
    claim_ids: list[Id]
    coverage: Literal["complete", "incomplete"]


class TradeOff(ContractModel):
    """Explain a benefit and cost trade-off against an alternative supplier."""

    trade_off_id: Id
    preferred_supplier_id: Id
    alternative_supplier_id: Id
    benefit_claim_ids: list[Id]
    cost_claim_ids: list[Id]
    uncertainty_ids: list[Id]
    text: str


class Negotiation(ContractModel):
    """Suggest a negotiation action without predicting an outcome."""

    negotiation_id: Id
    supplier_id: Id
    kind: Literal["suggestion"]
    action: Id
    basis_claim_ids: list[Id]
    expected_outcome: None = None


class DecisionRisk(ContractModel):
    """Describe a risk included in the final decision proposal."""

    risk_id: Id
    supplier_ids: list[Id]
    risk_type: Id
    knowledge_status: Literal["known", "unknown"]
    severity: Literal["low", "medium", "high", "critical", "unknown"]
    claim_ids: list[Id]
    uncertainty_ids: list[Id]
    suggested_action: Id


class Uncertainty(ContractModel):
    """Disclose missing knowledge that may affect the recommendation."""

    uncertainty_id: Id
    supplier_ids: list[Id]
    description: Id
    impact: Id
    suggested_criticality: Literal["critical", "noncritical"]
    proposed_action: Id
    proposed_owner: str = "buyer"


class OpenQuestion(ContractModel):
    """Express a concrete question required to resolve an uncertainty."""

    question_id: Id
    supplier_ids: list[Id]
    uncertainty_ids: list[Id]
    question: Id
    proposed_owner: Id


class Assumption(ContractModel):
    """Disclose an assumption used while composing the proposal."""

    assumption_id: Id
    text: Id
    claim_ids: list[Id]
    uncertainty_ids: list[Id]


class DecisionProposal(ContractModel):
    """Carry the complete structured proposal that must pass Buyer HITL."""

    decision: Decision
    recommendation: Ranking
    claims: list[Claim]
    comparisons: list[Comparison]
    trade_offs: list[TradeOff]
    negotiation_points: list[Negotiation]
    risk_flags: list[DecisionRisk]
    uncertainties: list[Uncertainty]
    open_questions: list[OpenQuestion]
    assumptions: list[Assumption]


class EvidenceItem(ContractModel):
    """Link a human-readable recommendation rationale to source provenance."""

    field: str
    supplier_id: str
    source: dict[str, object] | None = None
    edited_by_human: bool = False
    low_confidence: bool = False
    original_value: object = None


class RankedSupplier(ContractModel):
    """Represent a compact ranked supplier used by legacy presentation code."""

    rank: int = Field(ge=1)
    supplier_id: str
    rationale: str
    evidence: list[EvidenceItem] = Field(default_factory=list)


class Recommendation(ContractModel):
    """Carry a compact ranked recommendation used by existing UI responses."""

    ranked: list[RankedSupplier] = Field(default_factory=list)
    top_n: int = Field(default=3, ge=3, le=5)
    error: str | None = None
    feedback_processed: bool = False
    feedback_history: list[str] = Field(default_factory=list)


__all__ = ["DecisionProposal", "RankedSupplier", "Recommendation"]
