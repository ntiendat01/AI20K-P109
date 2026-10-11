"""DecisionProposal JSON retry guards at the graph boundary."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from unittest.mock import Mock

from src.agents.graph import build_graph
from src.agents.nodes.decision_llm import BUYER_DECISION_FAILURE_MESSAGE, decision_proposal
from src.core.config import Settings
from src.services.evaluation.engine import Evaluator
from src.services.evaluation.store import EvaluationStore
from src.services.evaluation.workflow import EvaluationWorkflow
from tests.fixtures.evaluation_cases import adapter, context, proposal

decision_module = importlib.import_module("src.agents.nodes.decision_llm")


@dataclass
class Response:
    content: str


class SequenceModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[object] = []

    def invoke(self, messages: object) -> Response:
        self.calls.append(messages)
        return Response(self.responses[len(self.calls) - 1])


@dataclass
class UsageResponse:
    content: str
    response_metadata: dict[str, object]


class UsageModel:
    def invoke(self, _messages: object) -> UsageResponse:
        return UsageResponse(
            proposal().model_dump_json(),
            {"token_usage": {"prompt_tokens": 123, "completion_tokens": 45}},
        )


def _state() -> dict[str, object]:
    return {
        "case_id": "case-demo",
        "pr_data": {"target_uom": "cái", "target_currency": "USD"},
        "normalized_quotes": [],
        "decision_context": {},
    }


def test_invalid_json_is_corrected_once_before_the_valid_proposal(monkeypatch):
    monkeypatch.setattr(
        decision_module,
        "get_settings",
        lambda: Settings(_env_file=None, decision_llm_json_retries=2),
    )
    model = SequenceModel(["not json", proposal().model_dump_json()])

    result = decision_proposal(_state(), llm=model)

    assert result["decision_retry_count"] == 1
    assert result["decision_proposal"] == proposal().model_dump(mode="json")
    assert len(model.calls) == 2
    assert "Chỉ trả một JSON object hợp lệ" in model.calls[1][-1]["content"]


def test_decision_observability_keeps_provider_tokens_when_available(monkeypatch):
    monkeypatch.setattr(
        decision_module,
        "get_settings",
        lambda: Settings(_env_file=None, decision_llm_json_retries=0),
    )

    result = decision_proposal(_state(), llm=UsageModel())

    assert result["decision_observability"]["prompt_tokens"] == 123
    assert result["decision_observability"]["completion_tokens"] == 45
    assert result["decision_observability"]["latency_ms"] is not None


def test_three_invalid_outputs_end_before_evaluation(monkeypatch, tmp_path):
    monkeypatch.setattr(
        decision_module,
        "get_settings",
        lambda: Settings(_env_file=None, decision_llm_json_retries=2),
    )
    model = SequenceModel(["{}", "[]", "still not json"])
    workflow = EvaluationWorkflow(Evaluator(adapter(), backoff_seconds=0), EvaluationStore(tmp_path / "review.sqlite"))
    submit = Mock(wraps=workflow.submit)
    monkeypatch.setattr(workflow, "submit", submit)
    graph = build_graph(
        evaluation_workflow=workflow,
        context_provider=lambda state: context(),
        confirmed_input=True,
        decision_model=model,
    )

    result = graph.invoke(_state(), {"configurable": {"thread_id": "invalid-decision"}})

    assert result["workflow_status"] == "technical_failure"
    assert result["message"] == BUYER_DECISION_FAILURE_MESSAGE
    assert result["decision_retry_count"] == 2
    assert "decision_proposal" not in result
    assert len(model.calls) == 3
    submit.assert_not_called()


def test_unverified_risk_claim_is_retained_only_as_a_disclosure(monkeypatch):
    monkeypatch.setattr(
        decision_module,
        "get_settings",
        lambda: Settings(_env_file=None, decision_llm_json_retries=0),
    )
    raw = proposal().model_dump(mode="json")
    raw["claims"].append(
        {
            "claim_id": "risk-unverified",
            "category": "risk",
            "supplier_ids": ["A"],
            "text": "Có thể có rủi ro chất lượng chưa xác minh.",
            "predicate": {
                "operator": "meets_criterion",
                "metric": "quality",
                "criterion": "quality_review",
                "source_requirement": "independent_assessment",
                "value": False,
            },
            "knowledge_status": "unknown",
            "suggested_action": "Yêu cầu thông tin bổ sung.",
        }
    )
    raw["decision"]["supporting_claim_ids"].append("risk-unverified")
    model = SequenceModel([json.dumps(raw)])

    result = decision_proposal(_state(), llm=model)

    assert "risk-unverified" not in {claim["claim_id"] for claim in result["decision_proposal"]["claims"]}
    assert "risk-unverified" not in result["decision_proposal"]["decision"]["supporting_claim_ids"]


def test_fabricated_known_risk_is_not_allowed_to_block_a_verified_proposal(monkeypatch, tmp_path):
    """A model cannot relabel an unverified risk as known to force needs_input."""
    monkeypatch.setattr(
        decision_module,
        "get_settings",
        lambda: Settings(_env_file=None, decision_llm_json_retries=0),
    )
    raw = proposal().model_dump(mode="json")
    raw["claims"].append(
        {
            "claim_id": "risk-delivery-deadline",
            "category": "risk",
            "supplier_ids": ["A"],
            "text": "NCC A không đáp ứng hạn giao.",
            "predicate": {
                "operator": "meets_criterion",
                "metric": "quality",
                "criterion": "delivery_deadline_met",
                "source_requirement": "human_edit",
                "value": False,
            },
            "knowledge_status": "known",
            "suggested_action": "Xác nhận lại với NCC.",
        }
    )
    raw["decision"]["supporting_claim_ids"].append("risk-delivery-deadline")
    raw["risk_flags"].append(
        {
            "risk_id": "risk-delivery-deadline-flag",
            "supplier_ids": ["A"],
            "risk_type": "lead_time_exceeded",
            "knowledge_status": "known",
            "severity": "unknown",
            "claim_ids": ["risk-delivery-deadline"],
            "uncertainty_ids": [],
            "suggested_action": "Xác nhận lại với NCC.",
        }
    )
    raw["recommendation"]["ranked"][0]["risk_ids"].append("risk-delivery-deadline-flag")

    result = decision_proposal(_state(), llm=SequenceModel([json.dumps(raw)]))
    cleaned = result["decision_proposal"]

    assert "risk-delivery-deadline" not in {claim["claim_id"] for claim in cleaned["claims"]}
    assert "risk-delivery-deadline" not in cleaned["decision"]["supporting_claim_ids"]
    assert "risk-delivery-deadline-flag" not in {risk["risk_id"] for risk in cleaned["risk_flags"]}
    assert "risk-delivery-deadline-flag" not in cleaned["recommendation"]["ranked"][0]["risk_ids"]

    workflow = EvaluationWorkflow(Evaluator(adapter(), backoff_seconds=0), EvaluationStore(tmp_path / "review.sqlite"))
    assert workflow.submit(cleaned, context()).overall_status == "ready_for_review"
