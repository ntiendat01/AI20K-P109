"""Pure decision, feasibility, policy and anchored quality gates."""

from __future__ import annotations

import re

from src.domain.analysis.evaluation import (
    ConstraintResult,
    DecisionProposal,
    Issue,
    Quality,
    RuntimeEvaluationContext,
)


def issue(stage: str, code: str, action: str = "REPAIR_OUTPUT", *, claims=(), suppliers=()) -> Issue:
    """Create stable issue identities suitable for repair-loop detection."""
    return Issue(
        issue_id=f"{stage}:{code}:{','.join(claims)}:{','.join(suppliers)}",
        stage=stage,
        code=code,
        action=action,
        claim_ids=list(claims),
        supplier_ids=list(suppliers),
        owner="decision_llm" if action == "REPAIR_OUTPUT" else "application",
    )


def validate_decision(proposal: DecisionProposal, context: RuntimeEvaluationContext) -> list[Issue]:
    """Validate untrusted identifiers, reference graph, ranking and assertion inventory."""
    problems: list[Issue] = []
    groups = {
        "claim": (proposal.claims, "claim_id"),
        "comparison": (proposal.comparisons, "comparison_id"),
        "trade_off": (proposal.trade_offs, "trade_off_id"),
        "risk": (proposal.risk_flags, "risk_id"),
        "uncertainty": (proposal.uncertainties, "uncertainty_id"),
        "negotiation": (proposal.negotiation_points, "negotiation_id"),
        "question": (proposal.open_questions, "question_id"),
        "assumption": (proposal.assumptions, "assumption_id"),
    }
    ids = {kind: [getattr(x, field) for x in objects] for kind, (objects, field) in groups.items()}
    all_ids = [value for values in ids.values() for value in values]
    if len(all_ids) != len(set(all_ids)):
        problems.append(issue("decision", "DUPLICATE_ID"))

    def walk(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
        if not isinstance(value, dict):
            return
        for field, item in value.items():
            if field.endswith("supplier_id") and item is not None and item not in context.candidate_ids:
                problems.append(issue("decision", "SUPPLIER_OUT_OF_SCOPE"))
            if field == "supplier_ids" and (
                not item or len(item) != len(set(item)) or not set(item) <= set(context.candidate_ids)
            ):
                problems.append(issue("decision", "SUPPLIER_SCOPE_INVALID"))
            if field.endswith("_ids"):
                kind = next((key for key in ids if field.endswith(f"{key}_ids")), None)
                if kind and (len(item) != len(set(item)) or not set(item) <= set(ids[kind])):
                    problems.append(issue("decision", "DANGLING_OR_DUPLICATE_REFERENCE"))
            walk(item)

    walk(proposal.model_dump())
    ranked = proposal.recommendation.ranked
    if proposal.decision.type == "ranked_recommendation":
        if not ranked or proposal.decision.preferred_supplier_id != ranked[0].supplier_id:
            problems.append(issue("decision", "PREFERRED_RANK_MISMATCH"))
        if [x.rank for x in ranked] != list(range(1, len(ranked) + 1)) or len({x.supplier_id for x in ranked}) != len(
            ranked
        ):
            problems.append(issue("decision", "INVALID_RANKS"))
        # At this gate only application-owned candidates are known. Constraint
        # feasibility is checked in the following gate.
        expected = min(context.top_n, len(context.candidate_ids))
        if proposal.recommendation.top_n != context.top_n or len(ranked) != expected:
            problems.append(issue("decision", "TOP_N_MISMATCH"))
        shortfall = proposal.recommendation.shortfall
        if len(context.candidate_ids) < context.top_n:
            if (
                shortfall is None
                or shortfall.requested_count != context.top_n
                or shortfall.returned_count != len(ranked)
                or shortfall.available_count != len(context.candidate_ids)
            ):
                problems.append(issue("decision", "INVALID_SHORTFALL"))
        elif shortfall is not None:
            problems.append(issue("decision", "UNEXPECTED_SHORTFALL"))
    elif ranked or proposal.decision.preferred_supplier_id is not None:
        problems.append(issue("decision", "NON_RANKING_HAS_RANKS"))

    claim_map = {c.claim_id: c for c in proposal.claims}
    context_tco = {
        fact.supplier_id: fact
        for fact in context.facts
        if fact.metric == "tco" and fact.value is not None and not isinstance(fact.value, bool)
    }
    for claim in proposal.claims:
        if claim.category != "quantitative" or claim.predicate.metric != "tco":
            continue
        fact = context_tco.get(claim.supplier_ids[0])
        if fact is None or claim.predicate.value != fact.value or claim.predicate.unit != fact.unit:
            problems.append(issue("decision", "TCO_CLAIM_MISMATCH", claims=[claim.claim_id]))

    unknown_risk_claims = {
        claim.claim_id for claim in proposal.claims if claim.category == "risk" and claim.knowledge_status == "unknown"
    }
    if unknown_risk_claims:
        referenced_claim_ids: set[str] = set()

        def collect_claim_references(value: object) -> None:
            if isinstance(value, list):
                for item in value:
                    collect_claim_references(item)
            elif isinstance(value, dict):
                for field, item in value.items():
                    if field.endswith("claim_ids") and isinstance(item, list):
                        referenced_claim_ids.update(reference for reference in item if isinstance(reference, str))
                    collect_claim_references(item)

        collect_claim_references(proposal.model_dump(mode="json"))
        used_unknown_risks = sorted(unknown_risk_claims & referenced_claim_ids)
        code = "UNKNOWN_RISK_USED_AS_SUPPORT" if used_unknown_risks else "UNKNOWN_RISK_AS_ASSERTION"
        problems.append(issue("decision", code, claims=used_unknown_risks or sorted(unknown_risk_claims)))

    for ranked_item in ranked:
        if any(
            r in claim_map and ranked_item.supplier_id not in claim_map[r].supplier_ids
            for r in ranked_item.rationale_claim_ids
        ):
            problems.append(issue("decision", "RATIONALE_SUPPLIER_MISMATCH"))
    for comparison in proposal.comparisons:
        if any(r in claim_map and claim_map[r].predicate.metric != comparison.criterion for r in comparison.claim_ids):
            problems.append(issue("decision", "COMPARISON_METRIC_MISMATCH"))
    for trade_off in proposal.trade_offs:
        if proposal.decision.type == "ranked_recommendation" and (
            trade_off.preferred_supplier_id != proposal.decision.preferred_supplier_id
            or trade_off.alternative_supplier_id == trade_off.preferred_supplier_id
        ):
            problems.append(issue("decision", "INVALID_TRADE_OFF_SCOPE"))
    for claim in proposal.claims:
        if claim.category != "comparison" and len(claim.supplier_ids) != 1:
            problems.append(issue("decision", "NON_ATOMIC_CLAIM", claims=[claim.claim_id]))
        if claim.category == "comparison":
            p = claim.predicate
            if set(claim.supplier_ids) != set(context.candidate_ids) or p.subject_supplier_id not in claim.supplier_ids:
                problems.append(issue("decision", "INCOMPLETE_COMPARISON_SCOPE", claims=[claim.claim_id]))
            if p.operator in {"greater_than", "less_than"} and (
                p.other_supplier_id not in claim.supplier_ids or p.other_supplier_id == p.subject_supplier_id
            ):
                problems.append(issue("decision", "INVALID_COMPARISON_PAIR", claims=[claim.claim_id]))
        if any(f not in context.formula_allowlist for f in claim.calculation_hints):
            problems.append(issue("decision", "FORMULA_NOT_ALLOWED", claims=[claim.claim_id]))

    # The inventory is conservative for numbers; arbitrary prose is never rendered
    # as verified fact. The review renderer builds statements from checked predicates.
    prose = [(proposal.decision.summary, proposal.decision.supporting_claim_ids)]
    prose += [(r.rationale, r.rationale_claim_ids) for r in ranked]
    prose += [(t.text, t.benefit_claim_ids + t.cost_claim_ids) for t in proposal.trade_offs]
    prose += [(a.text, a.claim_ids) for a in proposal.assumptions]
    for text, references in prose:
        if not references:
            if proposal.decision.type == "ranked_recommendation" and text.strip():
                problems.append(issue("decision", "ASSERTION_WITHOUT_CLAIM"))
            continue
        declared = " ".join(claim_map[r].text for r in references if r in claim_map)
        referenced_metrics = {claim_map[r].predicate.metric for r in references if r in claim_map}
        for metric, pattern in {
            "quality": r"\bquality\b|chất lượng",
            "compliance": r"\bcompliance\b|\bcertified\b|tuân thủ|chứng nhận",
        }.items():
            if re.search(pattern, text, flags=re.IGNORECASE) and metric not in referenced_metrics:
                problems.append(issue("decision", "UNDECLARED_QUALITATIVE_ASSERTION"))
        if not set(re.findall(r"\d+(?:[.,]\d+)*", text)) <= set(re.findall(r"\d+(?:[.,]\d+)*", declared)):
            problems.append(issue("decision", "UNDECLARED_NUMERIC_ASSERTION"))
    for risk in proposal.risk_flags:
        if (risk.knowledge_status == "known" and not risk.claim_ids) or (
            risk.knowledge_status == "unknown" and not risk.uncertainty_ids
        ):
            problems.append(issue("decision", "RISK_WITHOUT_BASIS"))
    return problems


def constraint_outcomes(context: RuntimeEvaluationContext) -> tuple[list[ConstraintResult], set[str], set[str]]:
    """Return all per-supplier outcomes, viable and unresolved candidate IDs."""
    facts = {(f.supplier_id, f.metric): f for f in context.facts}
    results: list[ConstraintResult] = []
    failed: set[str] = set()
    unknown: set[str] = set()
    for supplier in context.candidate_ids:
        for constraint in context.constraints:
            fact = facts.get((supplier, constraint.metric))
            if constraint.supplier_ids and supplier not in constraint.supplier_ids:
                status = "not_applicable"
            elif fact is None or fact.value is None or fact.unit != constraint.unit:
                status = "unknown"
            else:
                checks = {
                    "lte": fact.value <= constraint.value,
                    "gte": fact.value >= constraint.value,
                    "equals": fact.value == constraint.value,
                }
                status = "pass" if checks[constraint.operator] else "fail"
            results.append(
                ConstraintResult(constraint_id=constraint.constraint_id, supplier_id=supplier, status=status)
            )
            if constraint.hard and status == "fail":
                failed.add(supplier)
            if constraint.hard and status == "unknown":
                unknown.add(supplier)
    return results, set(context.candidate_ids) - failed - unknown, unknown - failed


def validate_constraints(
    proposal: DecisionProposal, context: RuntimeEvaluationContext
) -> tuple[list[Issue], list[ConstraintResult]]:
    results, viable, unknown = constraint_outcomes(context)
    problems: list[Issue] = []
    if not viable and not unknown:
        return [issue("constraint", "NO_VIABLE_SUPPLIER", "REPORT_NO_VIABLE_SUPPLIER")], results
    if unknown:
        problems.append(issue("constraint", "MANDATORY_FACT_UNKNOWN", "REQUEST_DATA", suppliers=sorted(unknown)))
    if not unknown and proposal.decision.type == "ranked_recommendation":
        shortfall = proposal.recommendation.shortfall
        if len(proposal.recommendation.ranked) != min(context.top_n, len(viable)) or (
            shortfall and shortfall.available_count != len(viable)
        ):
            problems.append(issue("constraint", "VIABLE_TOP_N_MISMATCH"))
    for ranked in proposal.recommendation.ranked:
        if ranked.supplier_id not in viable and ranked.supplier_id not in unknown:
            problems.append(issue("constraint", "RANKED_INFEASIBLE_SUPPLIER", suppliers=[ranked.supplier_id]))
    if proposal.decision.type == "no_viable_supplier" and viable:
        problems.append(issue("constraint", "FALSE_NO_VIABLE"))
    if (
        proposal.decision.type == "insufficient_candidates"
        and len(viable) >= context.minimum_candidates
        and not unknown
    ):
        problems.append(issue("constraint", "FALSE_INSUFFICIENT_CANDIDATES"))
    soft_ids = {c.constraint_id: c for c in context.constraints if not c.hard}
    claims = {c.claim_id: c for c in proposal.claims}
    for result in results:
        if result.constraint_id in soft_ids and result.status in {"fail", "unknown"}:
            metric = soft_ids[result.constraint_id].metric
            disclosed = any(
                result.supplier_id in {t.preferred_supplier_id, t.alternative_supplier_id}
                and any(r in claims and claims[r].predicate.metric == metric for r in t.cost_claim_ids)
                for t in proposal.trade_offs
            )
            if not disclosed:
                problems.append(issue("constraint", "SOFT_CONSTRAINT_NOT_DISCLOSED", suppliers=[result.supplier_id]))
    return problems, results


def validate_business(proposal: DecisionProposal, context: RuntimeEvaluationContext) -> list[Issue]:
    problems: list[Issue] = []
    ranked = proposal.decision.type == "ranked_recommendation"
    _, viable, _ = constraint_outcomes(context)
    if ranked and len(viable) < context.minimum_candidates:
        exception = next((r for r in context.rules if r.rule_id == "minimum_candidates"), None)
        granted = (
            exception
            and exception.exception_allowed
            and exception.exception_authority
            and exception.exception_authorized
            and exception.exception_granted_by
        )
        if not granted:
            action = (
                "REQUEST_EXCEPTION"
                if exception and exception.exception_allowed and exception.exception_authority
                else "REQUEST_DATA"
            )
            problems.append(issue("business_rule", "INSUFFICIENT_CANDIDATES", action))
    for rule in context.rules:
        if rule.status == "unknown":
            problems.append(issue("business_rule", f"RULE_UNKNOWN:{rule.rule_id}", "REQUEST_DATA"))
        if rule.status == "fail" and not (
            rule.exception_allowed
            and rule.exception_authority
            and rule.exception_authorized
            and rule.exception_granted_by
        ):
            action = "REQUEST_EXCEPTION" if rule.exception_allowed and rule.exception_authority else "REQUEST_DATA"
            problems.append(issue("business_rule", f"RULE_FAILED:{rule.rule_id}", action))
    claims = {c.claim_id: c for c in proposal.claims}
    for metric in context.mandatory_comparisons:
        matches = [c for c in proposal.comparisons if c.criterion == metric]
        complete = any(
            c.coverage == "complete"
            and set(c.supplier_ids) == set(context.candidate_ids)
            and any(
                r in claims and claims[r].category == "comparison" and claims[r].predicate.metric == metric
                for r in c.claim_ids
            )
            for c in matches
        )
        if ranked and not complete:
            facts_available = all(
                any(f.supplier_id == supplier and f.metric == metric and f.value is not None for f in context.facts)
                for supplier in context.candidate_ids
            )
            problems.append(
                issue(
                    "business_rule",
                    "MISSING_MANDATORY_COMPARISON",
                    "REPAIR_OUTPUT" if facts_available else "REQUEST_DATA",
                )
            )
    for metric in context.optional_metrics:
        known = {f.supplier_id for f in context.facts if f.metric == metric and f.value is not None}
        if known != set(context.candidate_ids):
            used = {r for item in proposal.recommendation.ranked for r in item.rationale_claim_ids}
            used.update(proposal.decision.supporting_claim_ids)
            if any(c.claim_id in used and c.predicate.metric == metric for c in proposal.claims):
                problems.append(issue("business_rule", "UNAVAILABLE_DATA_ADVANTAGE"))
    disclosed = {
        u.uncertainty_id
        for u in proposal.uncertainties
        if u.impact.strip() and u.proposed_action.strip() and u.proposed_owner.strip()
    }
    required = set(context.critical_uncertainty_ids)
    if not required <= disclosed or not required <= set(proposal.decision.uncertainty_ids):
        problems.append(issue("business_rule", "CRITICAL_UNCERTAINTY_HIDDEN"))
    if proposal.decision.type in {"needs_input", "insufficient_candidates"}:
        # ``needs_input`` is valid only when the application context actually
        # lacks a required fact.  If all mandatory comparisons and hard
        # constraints are available, this is an LLM output mistake; sending a
        # buyer back to edit already-confirmed quotes creates an endless loop.
        required_metrics = set(context.mandatory_comparisons)
        required_metrics.update(constraint.metric for constraint in context.constraints if constraint.hard)
        facts = {(fact.supplier_id, fact.metric): fact for fact in context.facts}
        _, _, unresolved_constraints = constraint_outcomes(context)
        data_complete = (
            len(context.candidate_ids) >= context.minimum_candidates
            and not unresolved_constraints
            and all(
                (fact := facts.get((supplier_id, metric))) is not None and fact.value is not None
                for supplier_id in context.candidate_ids
                for metric in required_metrics
            )
        )
        problems.append(
            issue(
                "business_rule",
                "DECISION_REQUESTS_INPUT",
                "REPAIR_OUTPUT" if data_complete else "REQUEST_DATA",
            )
        )
    return problems


def evaluate_quality(proposal: DecisionProposal, context: RuntimeEvaluationContext) -> tuple[Quality, list[Issue]]:
    """Anchors: 0 absent, 1 ungrounded/generic, 3 complete, 4 specific and actionable."""
    covered = {t.alternative_supplier_id for t in proposal.trade_offs if t.benefit_claim_ids and t.cost_claim_ids}
    quality = Quality(
        rationale_clarity=4
        if all(r.rationale_claim_ids and r.rationale.strip() for r in proposal.recommendation.ranked)
        else 1,
        comparison_completeness=4
        if set(context.mandatory_comparisons) <= {c.criterion for c in proposal.comparisons if c.coverage == "complete"}
        else 1,
        trade_off_usefulness=4 if set(context.material_alternative_ids) <= covered else 1,
        uncertainty_disclosure=4
        if all(
            u.impact.strip() and u.proposed_owner.strip() and u.proposed_action.strip() for u in proposal.uncertainties
        )
        else 1,
        actionability=4 if proposal.decision.preferred_supplier_id and proposal.decision.supporting_claim_ids else 1,
    )
    problems = (
        []
        if min(quality.model_dump().values()) >= context.quality_minimum
        else [issue("recommendation_quality", "QUALITY_BELOW_THRESHOLD")]
    )
    return quality, problems
