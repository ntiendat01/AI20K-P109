"""Deterministic evidence verification and Decimal replay, independent of similarity."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from src.application.evaluation.validation import issue
from src.domain.analysis.evaluation import (
    Chunk,
    Claim,
    DecisionProposal,
    EvidenceArtifact,
    Fact,
    Issue,
    RuntimeEvaluationContext,
    SourceFact,
)
from src.infrastructure.evaluation.evidence import SourceIntegrityError, authorized

METRIC_LABELS = {
    "tco": {"tco", "total cost", "tổng chi phí"},
    "price": {"price", "goods total", "giá"},
    "fee": {"fee", "shipping", "phí"},
    "quantity": {"quantity", "số lượng"},
    "delivery_days": {"delivery", "lead time", "giao hàng"},
    "warranty_months": {"warranty", "bảo hành"},
    "quality": {"quality", "chất lượng"},
    "compliance": {"compliance", "tuân thủ"},
}
UNIT_LABELS = {"calendar_day": {"calendar days", "calendar day", "ngày lịch"}, "month": {"months", "month", "tháng"}}


def bound_fact(fact: SourceFact, chunk: Chunk) -> bool:
    """Accept only a literal label/value/unit binding, not arbitrary extraction metadata."""
    if fact.value is None or fact.supplier_id != chunk.supplier_id:
        return False
    if fact.metric_text.casefold() not in METRIC_LABELS[fact.metric]:
        return False
    if fact.unit_text not in UNIT_LABELS.get(fact.unit, {fact.unit}):
        return False
    try:
        value_matches = (
            fact.value_text.lower() == str(fact.value).lower()
            if isinstance(fact.value, bool)
            else Decimal(fact.value_text) == fact.value
        )
    except InvalidOperation:
        return False
    if not value_matches:
        return False
    pattern = rf"(?<!\w){re.escape(fact.metric_text)}\s*[:=]?\s*{re.escape(fact.value_text)}\s*{re.escape(fact.unit_text)}(?!\w)"
    if not re.search(pattern, chunk.text, flags=re.IGNORECASE):
        return False
    if fact.time_origin and fact.time_origin.replace("_", " ").casefold() not in chunk.text.casefold():
        return False
    return all(condition.casefold() in chunk.text.casefold() for condition in fact.conditions)


def _same_context(a: Fact, b: Fact) -> bool:
    return (a.unit, a.time_origin, sorted(a.conditions), a.item_id, a.quote_id, a.criterion) == (
        b.unit,
        b.time_origin,
        sorted(b.conditions),
        b.item_id,
        b.quote_id,
        b.criterion,
    )


def _values(
    claim: Claim, artifact: EvidenceArtifact, context: RuntimeEvaluationContext
) -> tuple[dict[str, Fact], bool]:
    """Collect all relevant values, retaining conflicts; never pick the nearest match."""
    chunks = {source.chunk.chunk_id: source.chunk for source in artifact.sources}
    superseded = {
        c.original_chunk_id
        for c in chunks.values()
        if c.source_kind == "human_edit"
        and c.authenticated_edit_id in context.authorized_edit_ids
        and c.original_chunk_id in chunks
    }
    values: dict[str, Fact] = {}
    unresolved = False
    for supplier in claim.supplier_ids:
        facts: list[SourceFact] = []
        for chunk in chunks.values():
            if chunk.supplier_id != supplier or chunk.chunk_id in superseded:
                continue
            needed = [i for i in [chunk.parent_chunk_id, *chunk.context_chunk_ids] if i]
            if chunk.table_id and (not chunk.row_id or not chunk.cell_locator or not needed):
                unresolved = True
                continue
            if any(
                i not in chunks
                or chunks[i].document_hash != chunk.document_hash
                or chunks[i].document_id != chunk.document_id
                or chunks[i].supplier_id != supplier
                for i in needed
            ):
                unresolved = True
                continue
            if not chunk.context_complete and not needed:
                unresolved = True
                continue
            if chunk.source_kind == "human_edit" and (
                chunk.authenticated_edit_id not in context.authorized_edit_ids or chunk.original_chunk_id not in chunks
            ):
                unresolved = True
                continue
            relevant = [f for f in chunk.facts if f.metric == claim.predicate.metric]
            for fact in relevant:
                if not bound_fact(fact, chunk):
                    unresolved = True
                    continue
                if claim.category in {"qualitative", "risk"}:
                    p = claim.predicate
                    if (
                        chunk.source_kind != p.source_requirement
                        or fact.criterion != p.criterion
                        or p.criterion not in chunk.text
                    ):
                        unresolved = True
                        continue
                facts.append(fact)
        plans = [p for p in context.calculations if p.supplier_id == supplier and p.metric == claim.predicate.metric]
        for plan in plans:
            if plan.formula not in context.formula_allowlist or len(set(plan.operand_chunk_ids)) != len(
                plan.operand_chunk_ids
            ):
                unresolved = True
                continue
            operands = []
            for chunk_id in plan.operand_chunk_ids:
                chunk = chunks.get(chunk_id)
                matches = (
                    []
                    if chunk is None
                    else [
                        f
                        for f in chunk.facts
                        if f.supplier_id == supplier
                        and f.metric in {"price", "fee"}
                        and f.unit == plan.unit
                        and not isinstance(f.value, bool)
                        and bound_fact(f, chunk)
                    ]
                )
                if len(matches) != 1 or (chunk and (not chunk.context_complete or chunk.table_id)):
                    unresolved = True
                    break
                operands.append(matches[0].value)
            else:
                total = sum(operands, Decimal(0)).quantize(plan.quantum, rounding=ROUND_HALF_UP)
                facts.append(
                    SourceFact(
                        supplier_id=supplier,
                        metric=plan.metric,
                        value=total,
                        unit=plan.unit,
                        value_text=str(total),
                        metric_text="tco",
                        unit_text=plan.unit,
                    )
                )
        if facts:
            first = facts[0]
            if any(f.value != first.value or not _same_context(f, first) for f in facts):
                raise ConflictingEvidenceError
            values[supplier] = first
    return values, unresolved


class ConflictingEvidenceError(Exception):
    """Relevant sources disagree; all excerpts remain in the artifact."""


def verify_claim(claim: Claim, artifact: EvidenceArtifact, context: RuntimeEvaluationContext) -> EvidenceArtifact:
    verified = artifact.model_copy(deep=True)
    if (artifact.recommendation_id, artifact.recommendation_version, artifact.claim_id) != (
        context.recommendation_id,
        context.recommendation_version,
        claim.claim_id,
    ):
        raise SourceIntegrityError("Evidence envelope mismatch")
    for source in artifact.sources:
        chunk = source.chunk
        if (
            not authorized(chunk, context.source_scope, claim.supplier_ids)
            or not source.exact_excerpt
            or source.exact_excerpt not in chunk.text
            or source.context_excerpt not in chunk.text
        ):
            raise SourceIntegrityError("Invalid citation or source scope")
    verified.verification = {"source_revision_match": True, "scope_match": True, "exact_excerpt_match": True}
    if not artifact.sources:
        verified.support_status = "not_found"
        return verified
    try:
        values, unresolved = _values(claim, artifact, context)
    except ConflictingEvidenceError:
        verified.support_status = "contradicted"
        return verified
    if unresolved or set(values) != set(claim.supplier_ids):
        verified.support_status = "unresolved"
        return verified
    p = claim.predicate
    if claim.category == "quantitative":
        value = values[claim.supplier_ids[0]]
        matches = {
            "value_match": value.value == p.value,
            "unit_match": value.unit == p.unit,
            "condition_match": (value.time_origin, sorted(value.conditions), value.item_id, value.quote_id)
            == (p.time_origin, sorted(p.conditions), p.item_id, p.quote_id),
        }
    elif claim.category == "comparison":
        all_values = list(values.values())
        if not all(
            (v.unit, v.time_origin, sorted(v.conditions), v.item_id, v.criterion)
            == (
                all_values[0].unit,
                all_values[0].time_origin,
                sorted(all_values[0].conditions),
                all_values[0].item_id,
                all_values[0].criterion,
            )
            for v in all_values
        ):
            verified.support_status = "unresolved"
            return verified
        subject = values[p.subject_supplier_id].value
        if p.operator in {"minimum", "maximum"}:
            best = (min if p.operator == "minimum" else max)(v.value for v in all_values)
            tied = [supplier for supplier, fact in values.items() if fact.value == best]
            verified.tied_supplier_ids = tied if len(tied) > 1 else []
            match = subject == best and (len(tied) == 1 or p.tie_handling == "disclose")
        else:
            other = values[p.other_supplier_id].value
            match = subject > other if p.operator == "greater_than" else subject < other
        matches = {
            "value_match": match,
            "unit_match": True,
            "condition_match": True,
            "full_scope": set(values) == set(context.candidate_ids),
        }
    else:
        matches = {"value_match": values[claim.supplier_ids[0]].value == p.value, "criterion_match": True}
        if claim.category == "risk" and claim.knowledge_status == "unknown":
            verified.evidence_kind = "unknown_disclosure"
            verified.support_status = "unresolved"
            return verified
    verified.verification.update(matches)
    verified.support_status = "supported" if all(matches.values()) else "contradicted"
    return verified


def verify_grounding(
    proposal: DecisionProposal, artifacts: list[EvidenceArtifact], context: RuntimeEvaluationContext
) -> tuple[list[EvidenceArtifact], list[Issue]]:
    by_claim = {e.claim_id: e for e in artifacts}
    if len(by_claim) != len(artifacts) or set(by_claim) != {c.claim_id for c in proposal.claims}:
        raise SourceIntegrityError("Incomplete or duplicate evidence graph")
    verified = [verify_claim(c, by_claim[c.claim_id], context) for c in proposal.claims]
    mandatory = set(proposal.decision.supporting_claim_ids)
    mandatory.update(
        r
        for comparison in proposal.comparisons
        if comparison.criterion in context.mandatory_comparisons
        for r in comparison.claim_ids
    )
    problems = []
    for artifact in verified:
        if artifact.support_status == "supported":
            continue
        if artifact.support_status == "contradicted":
            code, action = "CONTRADICTED_CLAIM", "REPAIR_OUTPUT"
        elif artifact.claim_id in mandatory:
            code, action = "MANDATORY_SOURCE_UNRESOLVED", "REQUEST_DATA"
        else:
            code, action = "UNSUPPORTED_OPTIONAL_CLAIM", "REPAIR_OUTPUT"
        problems.append(issue("evidence_grounding", code, action, claims=[artifact.claim_id]))
    return verified, problems
