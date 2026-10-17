from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, Protocol, TypedDict, assert_never

from pydantic import JsonValue, ValidationError

from src.agents.state import ProcurementAgentState
from src.core.config import Settings, get_settings
from src.domain.agent.analysis.decision import (
    DecisionProposal,
    DecisionProposalStatus,
)
from src.domain.agent.analysis.tco import TCOCalculationStatus, TCOResult
from src.infrastructure.llm import get_llm, resolve_llm_provider

DEFAULT_TOP_N: Final = 3
MIN_TOP_N: Final = 1
MAX_TOP_N: Final = 5
JSON_FENCE: Final = chr(96) * 3
BUYER_DECISION_FAILURE_MESSAGE: Final = "Không thể tạo đề xuất mua sắm hợp lệ. Vui lòng thử lại."


class DecisionMessage(TypedDict):
    role: Literal["system", "user"]
    content: str


class DecisionModel(Protocol):
    def invoke(self, messages: list[DecisionMessage]) -> str | Mapping[str, JsonValue]: ...


@dataclass(frozen=True, slots=True)
class DecisionConstraints:
    allowed_supplier_ids: frozenset[str]
    expected_rank_count: int
    input_artifact_ids: tuple[str, ...]


def build_legacy_decision_payload(
    state: Mapping[str, object],
    risk_flags: list[object],
) -> dict[str, object]:
    """Build the previous evaluation contract payload without altering the agent node.

    The evaluation API still accepts this contract for historical recommendations,
    so its retry boundary remains available while current analysis uses
    :func:`decision_llm` above.
    """
    from src.domain.analysis.evaluation import DecisionProposal as LegacyDecisionProposal

    return {
        "schema": LegacyDecisionProposal.model_json_schema(),
        "top_n": state.get("pr_data", {}).get("top_n", DEFAULT_TOP_N)
        if isinstance(state.get("pr_data"), Mapping)
        else DEFAULT_TOP_N,
        "tco_results": list(state.get("tco_results", [])),
        "comparison_matrix": state.get("comparison_matrix", {}),
        "risk_flags": risk_flags,
        "confirmed_context": state.get("decision_context", {}),
    }


def build_decision_payload(
    state: Mapping[str, object],
    risk_flags: list[object],
) -> dict[str, object]:
    """Compact the historical prompt to fields that can support a decision claim."""
    payload = build_legacy_decision_payload(state, risk_flags)
    raw_results = payload["tco_results"]
    raw_matrix = payload["comparison_matrix"]
    raw_context = payload["confirmed_context"]

    compact_results = [
        {
            key: result[key]
            for key in (
                "supplier_id",
                "subtotal",
                "total_surcharges",
                "total_vat",
                "total_tco",
                "status",
                "missing_fields",
            )
            if key in result
        }
        for result in raw_results
        if isinstance(result, Mapping)
    ]
    compact_matrix = _compact_comparison_matrix(raw_matrix)
    compact_context = _compact_confirmed_context(raw_context)
    return {
        "schema": payload["schema"],
        "top_n": payload["top_n"],
        "tco_results": compact_results,
        "comparison_matrix": compact_matrix,
        "risk_flags": risk_flags,
        "confirmed_context": compact_context,
    }


def estimate_payload_tokens(payload: Mapping[str, object]) -> int:
    """Provide a stable, provider-neutral prompt size estimate for regression tests."""
    return (len(json.dumps(payload, ensure_ascii=False, default=str)) + 3) // 4


def decision_proposal(
    state: Mapping[str, object],
    *,
    llm: object | None = None,
) -> dict[str, object]:
    """Validate and retry the legacy DecisionProposal contract at its boundary.

    This adapter is deliberately isolated from ``decision_llm``.  New analysis
    runs use the agent proposal model; existing evaluation records retain their
    strict JSON retry and disclosure-only risk behavior.
    """
    from src.domain.analysis.evaluation import DecisionProposal as LegacyDecisionProposal

    settings = get_settings()
    messages: list[DecisionMessage] = [
        {"role": "system", "content": settings.evaluation_decision_prompt},
        {
            "role": "user",
            "content": json.dumps(build_decision_payload(state, []), ensure_ascii=False, default=str),
        },
    ]
    retry_count = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    started_at = time.perf_counter()

    for attempt in range(settings.decision_llm_json_retries + 1):
        response = _invoke_legacy_model(messages, llm)
        content, response_prompt_tokens, response_completion_tokens = _legacy_response_content(response)
        prompt_tokens = response_prompt_tokens if response_prompt_tokens is not None else prompt_tokens
        completion_tokens = response_completion_tokens if response_completion_tokens is not None else completion_tokens
        try:
            proposal = LegacyDecisionProposal.model_validate(_decode_legacy_json(content))
        except (TypeError, json.JSONDecodeError, ValidationError):
            if attempt == settings.decision_llm_json_retries:
                return _legacy_decision_failure(
                    retry_count=retry_count,
                    started_at=started_at,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            retry_count += 1
            messages.append(
                {
                    "role": "user",
                    "content": "Chỉ trả một JSON object hợp lệ, đúng schema đã cung cấp; không thêm markdown hay diễn giải.",
                }
            )
            continue

        cleaned = _remove_unsupported_legacy_risks(proposal.model_dump(mode="json"))
        try:
            validated = LegacyDecisionProposal.model_validate(cleaned)
        except ValidationError:
            return _legacy_decision_failure(
                retry_count=retry_count,
                started_at=started_at,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        return {
            "decision_proposal": validated.model_dump(mode="json"),
            "decision_retry_count": retry_count,
            "decision_observability": _legacy_observability(started_at, prompt_tokens, completion_tokens),
        }

    raise AssertionError("unreachable")


def decision_llm(
    state: ProcurementAgentState,
    *,
    llm: DecisionModel | None = None,
) -> ProcurementAgentState:
    tco_results = state.get("tco_results", [])
    comparison_matrix = state.get("comparison_matrix")
    eligible_supplier_ids = _eligible_supplier_ids(tco_results)
    input_artifact_ids = tuple(dict.fromkeys(result.quotation_revision_id for result in tco_results))
    constraints = DecisionConstraints(
        allowed_supplier_ids=frozenset(eligible_supplier_ids),
        expected_rank_count=min(_configured_top_n(state), len(eligible_supplier_ids)),
        input_artifact_ids=input_artifact_ids,
    )

    if not eligible_supplier_ids:
        return {"decision_proposal": _needs_input("Không có nhà cung cấp đủ dữ liệu TCO để xếp hạng.", constraints)}
    if comparison_matrix is None:
        return {"decision_proposal": _needs_input("Thiếu ma trận so sánh nhà cung cấp.", constraints)}

    supplier_names = _supplier_name_map(state, eligible_supplier_ids)
    settings = get_settings()
    messages: list[DecisionMessage] = [
        {"role": "system", "content": settings.decision_prompt},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "schema": DecisionProposal.model_json_schema(),
                    "allowed_supplier_ids": eligible_supplier_ids,
                    "supplier_names": supplier_names,
                    "top_n": constraints.expected_rank_count,
                    "tco_results": [result.model_dump(mode="json") for result in tco_results],
                    "comparison_matrix": comparison_matrix.model_dump(mode="json"),
                    "risk_flags": [risk.model_dump(mode="json") for risk in state.get("risk_flags", [])],
                    "input_artifact_ids": list(input_artifact_ids),
                },
                ensure_ascii=False,
            ),
        },
    ]
    raw_response = _invoke_model(messages, settings, llm)
    if raw_response is None:
        return {"decision_proposal": _needs_input("Chưa cấu hình mô hình quyết định.", constraints)}

    try:
        proposal = _decode_proposal(raw_response)
    except (json.JSONDecodeError, ValidationError):
        return {"decision_proposal": _needs_input("Phản hồi mô hình không đúng DecisionProposal.", constraints)}

    grounded = _ground_proposal(proposal, constraints)
    if grounded is None:
        grounded = _needs_input("Đề xuất mô hình tham chiếu dữ liệu ngoài analysis snapshot.", constraints)
    return {"decision_proposal": grounded}


def _invoke_model(
    messages: list[DecisionMessage],
    settings: Settings,
    llm: DecisionModel | None,
) -> str | Mapping[str, JsonValue] | None:
    if llm is not None:
        return llm.invoke(messages)
    if not _has_decision_provider(settings):
        return None
    return str(get_llm().invoke(messages).content)


def _supplier_name_map(state: ProcurementAgentState, allowed_supplier_ids: list[str]) -> dict[str, str]:
    """Expose display names to the decision model without changing server-owned IDs."""
    supplier_ids = state.get("confirmed_supplier_ids", [])
    confirmed_quotes = state.get("confirmed_quotes", [])
    if not isinstance(supplier_ids, list) or not isinstance(confirmed_quotes, list):
        return {}

    names: dict[str, str] = {}
    for supplier_id, quote in zip(supplier_ids, confirmed_quotes, strict=False):
        if supplier_id not in allowed_supplier_ids:
            continue
        supplier_name = getattr(quote, "supplier_name", None)
        if isinstance(supplier_name, str) and supplier_name.strip():
            names[supplier_id] = supplier_name.strip()
    return names


def _compact_comparison_matrix(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    matrix = value.get("matrix")
    compact_rows: dict[str, dict[str, dict[str, object]]] = {}
    if isinstance(matrix, Mapping):
        for supplier_id, row in matrix.items():
            if not isinstance(supplier_id, str) or not isinstance(row, Mapping):
                continue
            compact_rows[supplier_id] = {
                criterion: {"value": cell.get("value")}
                for criterion, cell in row.items()
                if isinstance(criterion, str) and isinstance(cell, Mapping)
            }
    return {
        "suppliers": list(value.get("suppliers", [])),
        "criteria": list(value.get("criteria", [])),
        "matrix": compact_rows,
    }


def _compact_confirmed_context(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    facts = value.get("facts", [])
    compact_facts = [
        {
            key: fact[key]
            for key in ("supplier_id", "metric", "value", "unit", "time_origin", "conditions", "criterion")
            if key in fact
        }
        for fact in facts
        if isinstance(fact, Mapping)
    ]
    return {
        "candidate_ids": list(value.get("candidate_ids", [])),
        "facts": compact_facts,
        "constraints": list(value.get("constraints", [])),
        "mandatory_comparisons": list(value.get("mandatory_comparisons", [])),
    }


def _invoke_legacy_model(messages: list[DecisionMessage], llm: object | None) -> object:
    if llm is not None:
        invoke = getattr(llm, "invoke", None)
        if callable(invoke):
            return invoke(messages)
        raise TypeError("Legacy decision model must expose invoke(messages)")
    settings = get_settings()
    if not _has_decision_provider(settings):
        raise TypeError("No decision model is configured")
    return get_llm().invoke(messages)


def _legacy_response_content(response: object) -> tuple[object, int | None, int | None]:
    if isinstance(response, (str, Mapping)):
        return response, None, None
    content = getattr(response, "content", None)
    metadata = getattr(response, "response_metadata", {})
    token_usage = metadata.get("token_usage", {}) if isinstance(metadata, Mapping) else {}
    prompt_tokens = token_usage.get("prompt_tokens") if isinstance(token_usage, Mapping) else None
    completion_tokens = token_usage.get("completion_tokens") if isinstance(token_usage, Mapping) else None
    return (
        content,
        prompt_tokens if isinstance(prompt_tokens, int) else None,
        completion_tokens if isinstance(completion_tokens, int) else None,
    )


def _decode_legacy_json(response: object) -> object:
    if isinstance(response, Mapping):
        return response
    if not isinstance(response, str):
        raise TypeError("Decision model response must contain JSON text")
    stripped = response.strip()
    if stripped.startswith(JSON_FENCE) and stripped.endswith(JSON_FENCE):
        stripped = "\n".join(stripped.splitlines()[1:-1])
    return json.loads(stripped)


def _remove_unsupported_legacy_risks(proposal: dict[str, object]) -> dict[str, object]:
    """Risk claims require verified source facts; otherwise retain only disclosures."""
    claims = proposal.get("claims", [])
    blocked_claim_ids = {
        claim.get("claim_id")
        for claim in claims
        if isinstance(claim, Mapping) and claim.get("category") == "risk" and isinstance(claim.get("claim_id"), str)
    }
    if not blocked_claim_ids:
        return proposal

    proposal["claims"] = [
        claim for claim in claims if not isinstance(claim, Mapping) or claim.get("claim_id") not in blocked_claim_ids
    ]
    _discard_claim_references(proposal, blocked_claim_ids)
    blocked_risk_ids = {
        risk.get("risk_id")
        for risk in proposal.get("risk_flags", [])
        if isinstance(risk, Mapping) and set(risk.get("claim_ids", [])) & blocked_claim_ids
    }
    proposal["risk_flags"] = [
        risk
        for risk in proposal.get("risk_flags", [])
        if not isinstance(risk, Mapping) or risk.get("risk_id") not in blocked_risk_ids
    ]
    recommendation = proposal.get("recommendation")
    if isinstance(recommendation, dict):
        for ranked in recommendation.get("ranked", []):
            if isinstance(ranked, dict):
                ranked["risk_ids"] = [
                    risk_id for risk_id in ranked.get("risk_ids", []) if risk_id not in blocked_risk_ids
                ]
    return proposal


def _discard_claim_references(proposal: dict[str, object], blocked_claim_ids: set[str]) -> None:
    decision = proposal.get("decision")
    if isinstance(decision, dict):
        decision["supporting_claim_ids"] = [
            claim_id for claim_id in decision.get("supporting_claim_ids", []) if claim_id not in blocked_claim_ids
        ]
    for collection, keys in {
        "comparisons": ("claim_ids",),
        "trade_offs": ("benefit_claim_ids", "cost_claim_ids"),
        "negotiation_points": ("basis_claim_ids",),
    }.items():
        for item in proposal.get(collection, []):
            if isinstance(item, dict):
                for key in keys:
                    item[key] = [claim_id for claim_id in item.get(key, []) if claim_id not in blocked_claim_ids]
    recommendation = proposal.get("recommendation")
    if isinstance(recommendation, dict):
        for ranked in recommendation.get("ranked", []):
            if isinstance(ranked, dict):
                ranked["rationale_claim_ids"] = [
                    claim_id for claim_id in ranked.get("rationale_claim_ids", []) if claim_id not in blocked_claim_ids
                ]


def _legacy_observability(
    started_at: float,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> dict[str, int | float | None]:
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_ms": (time.perf_counter() - started_at) * 1000,
    }


def _legacy_decision_failure(
    *,
    retry_count: int,
    started_at: float,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> dict[str, object]:
    return {
        "workflow_status": "technical_failure",
        "message": BUYER_DECISION_FAILURE_MESSAGE,
        "decision_retry_count": retry_count,
        "decision_observability": _legacy_observability(started_at, prompt_tokens, completion_tokens),
    }


def _decode_proposal(
    response: str | Mapping[str, JsonValue],
) -> DecisionProposal:
    match response:
        case str() as text:
            stripped = text.strip()
            if stripped.startswith(JSON_FENCE) and stripped.endswith(JSON_FENCE):
                lines = stripped.splitlines()
                stripped = "\n".join(lines[1:-1])
            raw = json.loads(stripped)
        case Mapping() as mapping:
            raw = mapping
        case unreachable:
            assert_never(unreachable)
    return DecisionProposal.model_validate(raw)


def _ground_proposal(
    proposal: DecisionProposal,
    constraints: DecisionConstraints,
) -> DecisionProposal | None:
    match proposal.status:
        case DecisionProposalStatus.NEEDS_INPUT:
            return _needs_input(proposal.rationale, constraints)
        case DecisionProposalStatus.PROPOSED:
            preferred = proposal.preferred_supplier_id
            ranked = proposal.ranked_supplier_ids
            valid_ranking = (
                preferred is not None
                and len(ranked) == constraints.expected_rank_count
                and len(ranked) == len(set(ranked))
                and ranked[0] == preferred
                and set(ranked) <= constraints.allowed_supplier_ids
            )
            valid_tradeoffs = all(
                tradeoff.preferred_supplier_id == preferred
                and tradeoff.alternative_supplier_id in constraints.allowed_supplier_ids
                and tradeoff.alternative_supplier_id != preferred
                for tradeoff in proposal.tradeoffs
            )
            if not valid_ranking or not valid_tradeoffs:
                return None
            return proposal.model_copy(update={"input_artifact_ids": list(constraints.input_artifact_ids)})
        case unreachable:
            assert_never(unreachable)


def _needs_input(
    rationale: str,
    constraints: DecisionConstraints,
) -> DecisionProposal:
    return DecisionProposal(
        status=DecisionProposalStatus.NEEDS_INPUT,
        rationale=rationale,
        input_artifact_ids=list(constraints.input_artifact_ids),
    )


def _eligible_supplier_ids(results: list[TCOResult]) -> list[str]:
    suppliers: list[str] = []
    for result in results:
        match result.status:
            case TCOCalculationStatus.CALCULATED:
                if result.total_tco is not None and result.supplier_id not in suppliers:
                    suppliers.append(result.supplier_id)
            case TCOCalculationStatus.MISSING_DATA:
                pass
            case unreachable:
                assert_never(unreachable)
    return suppliers


def _configured_top_n(state: ProcurementAgentState) -> int:
    value = state.get("pr_data", {}).get("top_n", DEFAULT_TOP_N)
    if isinstance(value, int) and not isinstance(value, bool) and MIN_TOP_N <= value <= MAX_TOP_N:
        return value
    return DEFAULT_TOP_N


def _has_decision_provider(settings: Settings) -> bool:
    configured = {
        "openrouter": settings.openrouter_api_key,
        "groq": settings.groq_api_key,
        "qwen": settings.qwen_base_url,
        "openai": settings.openai_api_key,
    }
    return bool(configured[resolve_llm_provider(settings)].strip())
