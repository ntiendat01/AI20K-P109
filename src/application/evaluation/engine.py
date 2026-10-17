"""Five ordered gates and deterministic routing for untrusted Decision LLM output."""

from __future__ import annotations

import time
from typing import Protocol

from pydantic import ValidationError

from src.application.evaluation.grounding import verify_grounding
from src.application.evaluation.validation import (
    evaluate_quality,
    issue,
    validate_business,
    validate_constraints,
    validate_decision,
)
from src.domain.analysis.evaluation import (
    Action,
    CheckResult,
    Chunk,
    DecisionProposal,
    EvaluationResult,
    EvidenceArtifact,
    RuntimeEvaluationContext,
    StageResult,
)
from src.infrastructure.evaluation.evidence import EvidenceUnavailableError, SourceIntegrityError

STAGES = ["decision", "constraint", "evidence_grounding", "business_rule", "recommendation_quality"]
CHECK_STAGES = {
    "NO_UNSUPPORTED_CLAIM": ["decision", "evidence_grounding"],
    "NO_MISSING_MANDATORY_COMPARISON": ["business_rule"],
    "ALL_NUMERICAL_CALCULATIONS_REPRODUCIBLE": ["evidence_grounding"],
    "ALL_RECOMMENDATION_CLAIMS_BACKED_BY_SOURCES": ["evidence_grounding"],
    "DECISION_RESPECTS_PROCUREMENT_POLICY": ["constraint", "business_rule"],
    "NO_SUPPLIER_ADVANTAGE_FROM_UNAVAILABLE_DATA": ["business_rule"],
    "CRITICAL_UNCERTAINTY_EXPLICITLY_DISCLOSED": ["constraint", "business_rule", "recommendation_quality"],
}
ROUTES = {
    "RETRY_TRANSIENT": ("technical_failure", "retry_transient"),
    "REQUEST_DATA": ("needs_input", "awaiting_input"),
    "REQUEST_EXCEPTION": ("exception_required", "awaiting_authorized_exception"),
    "REPORT_NO_VIABLE_SUPPLIER": ("no_viable_supplier", "awaiting_resolution"),
    "ESCALATE_REPAIR_LIMIT": ("needs_input", "manual_resolution"),
    "REPAIR_OUTPUT": ("repairable", "repair_decision_llm"),
}
PRIORITY = list(ROUTES)


class EvidenceRetriever(Protocol):
    def ingest(self, chunks: list[Chunk]) -> None: ...
    def retrieve(self, proposal: DecisionProposal, context: RuntimeEvaluationContext) -> list[EvidenceArtifact]: ...


class Evaluator:
    def __init__(
        self, retriever: EvidenceRetriever, *, service_retries: int = 2, backoff_seconds: float = 0.05
    ) -> None:
        if service_retries < 0 or backoff_seconds < 0:
            raise ValueError("Retry limits must be nonnegative")
        self.retriever, self.service_retries, self.backoff_seconds = retriever, service_retries, backoff_seconds

    def evaluate(self, output: object, context: RuntimeEvaluationContext, *, attempt: int = 1) -> EvaluationResult:
        """Never call a judge before mandatory gates pass, never repair a source failure."""
        start = time.perf_counter()
        result = EvaluationResult(
            evaluation_id=f"eval:{context.recommendation_id}:{context.recommendation_version}:{attempt}",
            recommendation_id=context.recommendation_id,
            recommendation_version=context.recommendation_version,
            attempt=attempt,
            overall_status="ready_for_review",
            stage_results=[StageResult(stage=s, status="not_run") for s in STAGES],
            check_results=[],
            issues=[],
            required_actions=[],
        )
        try:
            proposal = DecisionProposal.model_validate(output)
        except ValidationError:
            proposal = None
            result.issues = [issue("decision", "INVALID_OUTPUT_CONTRACT")]
            result.stage_results[0].status = "fail"
        else:
            for index, stage in enumerate(STAGES):
                try:
                    if stage == "decision":
                        problems = validate_decision(proposal, context)
                    elif stage == "constraint":
                        problems, result.constraint_results = validate_constraints(proposal, context)
                    elif stage == "evidence_grounding":
                        artifacts = self._retrieve(proposal, context)
                        result.evidence, problems = verify_grounding(proposal, artifacts, context)
                    elif stage == "business_rule":
                        problems = validate_business(proposal, context)
                    else:
                        result.quality, problems = evaluate_quality(proposal, context)
                except SourceIntegrityError:
                    problems = [issue(stage, "SOURCE_INTEGRITY", "RETRY_TRANSIENT")]
                except EvidenceUnavailableError:
                    problems = [issue(stage, "EVIDENCE_SERVICE_EXHAUSTED", "RETRY_TRANSIENT")]
                result.stage_results[index].status = "fail" if problems else "pass"
                result.issues.extend(problems)
                if problems:
                    break
        self._route(result, proposal)
        result.latency_ms = (time.perf_counter() - start) * 1000
        return result

    def _retrieve(self, proposal: DecisionProposal, context: RuntimeEvaluationContext) -> list[EvidenceArtifact]:
        for retry in range(self.service_retries + 1):
            try:
                return self.retriever.retrieve(proposal, context)
            except EvidenceUnavailableError:
                if retry == self.service_retries:
                    raise
                time.sleep(min(self.backoff_seconds * 2**retry, 5))
        raise AssertionError("unreachable")

    @staticmethod
    def _route(result: EvaluationResult, proposal: DecisionProposal | None = None) -> None:
        result.issues = list({i.issue_id: i for i in result.issues}.values())
        for stage in result.stage_results:
            stage.issue_ids = [i.issue_id for i in result.issues if i.stage == stage.stage]
        for check_id, stages in CHECK_STAGES.items():
            selected = [s for s in result.stage_results if s.stage in stages]
            status = (
                "fail"
                if any(s.status == "fail" for s in selected)
                else "not_run"
                if any(s.status == "not_run" for s in selected)
                else "pass"
            )
            result.check_results.append(
                CheckResult(check_id=check_id, status=status, issue_ids=[i for s in selected for i in s.issue_ids])
            )
        # Check verdicts are independent: a failed optional qualitative claim does
        # not make already-replayed arithmetic fail, nor does a policy exception
        # imply that a mandatory comparison is absent.
        by_stage = {s.stage: s.status for s in result.stage_results}
        independent = {
            "NO_MISSING_MANDATORY_COMPARISON": {"MISSING_MANDATORY_COMPARISON"},
            "NO_SUPPLIER_ADVANTAGE_FROM_UNAVAILABLE_DATA": {"UNAVAILABLE_DATA_ADVANTAGE"},
            "CRITICAL_UNCERTAINTY_EXPLICITLY_DISCLOSED": {"CRITICAL_UNCERTAINTY_HIDDEN"},
        }
        for check in result.check_results:
            if check.check_id in independent and by_stage["business_rule"] != "not_run":
                relevant = [i for i in result.issues if i.code in independent[check.check_id]]
                check.status = "fail" if relevant else "pass"
                check.issue_ids = [i.issue_id for i in relevant]
            if check.check_id == "ALL_NUMERICAL_CALCULATIONS_REPRODUCIBLE" and proposal and result.evidence:
                numerical = {c.claim_id for c in proposal.claims if c.category in {"quantitative", "comparison"}}
                checked = {e.claim_id for e in result.evidence if e.support_status == "supported"}
                check.status = "pass" if numerical <= checked else "fail"
                check.issue_ids = [i.issue_id for i in result.issues if set(i.claim_ids) & (numerical - checked)]
        if not result.issues:
            result.required_actions = [Action(action_id="review", type="PRESENT_FOR_REVIEW", route="hitl_2")]
            return
        actions = sorted({i.action for i in result.issues}, key=PRIORITY.index)
        result.overall_status = ROUTES[actions[0]][0]
        result.required_actions = [
            Action(
                action_id=f"action:{action}",
                type=action,
                route=ROUTES[action][1],
                issue_ids=[i.issue_id for i in result.issues if i.action == action],
            )
            for action in actions
        ]
        if any(i.code in {"SOURCE_INTEGRITY", "EVIDENCE_SERVICE_EXHAUSTED"} for i in result.issues):
            result.required_actions[0].route = "technical_failure"


def render_review(
    proposal: DecisionProposal, result: EvaluationResult, context: RuntimeEvaluationContext
) -> dict[str, object]:
    """Construct factual UI content from verified predicates; discard free-form LLM prose."""
    if result.overall_status != "ready_for_review" or (result.recommendation_id, result.recommendation_version) != (
        context.recommendation_id,
        context.recommendation_version,
    ):
        raise ValueError("Only the current verified recommendation is reviewable")
    verified = {e.claim_id: e for e in result.evidence if e.support_status == "supported"}
    claims = {}
    for claim in proposal.claims:
        if claim.claim_id not in verified:
            raise ValueError("Review contains an unverified claim")
        claims[claim.claim_id] = {
            "supplier_ids": claim.supplier_ids,
            "predicate": claim.predicate.model_dump(mode="json"),
            "evidence": verified[claim.claim_id].model_dump(mode="json"),
        }
    return {
        "checkpoint": "recommendation_review",
        "recommendation_id": context.recommendation_id,
        "recommendation_version": context.recommendation_version,
        "preferred_supplier_id": proposal.decision.preferred_supplier_id,
        "ranked": [
            {
                "rank": r.rank,
                "supplier_id": r.supplier_id,
                "claim_ids": r.rationale_claim_ids,
                "trade_off_ids": r.trade_off_ids,
            }
            for r in proposal.recommendation.ranked
        ],
        "claims": claims,
        "trade_offs": [
            {
                "trade_off_id": t.trade_off_id,
                "preferred_supplier_id": t.preferred_supplier_id,
                "alternative_supplier_id": t.alternative_supplier_id,
                "benefit_claim_ids": t.benefit_claim_ids,
                "cost_claim_ids": t.cost_claim_ids,
            }
            for t in proposal.trade_offs
        ],
        "uncertainties": [u.model_dump(mode="json") for u in proposal.uncertainties],
        "critical_uncertainty_ids": context.critical_uncertainty_ids,
        "negotiation_points": [
            {
                "kind": "suggestion",
                "supplier_id": n.supplier_id,
                "basis_claim_ids": n.basis_claim_ids,
                "proposed_action": n.action,
                "is_supplier_commitment": False,
            }
            for n in proposal.negotiation_points
        ],
    }
