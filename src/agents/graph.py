from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, assert_never

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.nodes.analysis_tools import (
    analyze_risks_node,
    calculate_tco_node,
    compare_suppliers_node,
)
from src.agents.nodes.confidence_router import confidence_router
from src.agents.nodes.decision_llm import DecisionModel, decision_llm, decision_proposal
from src.agents.nodes.extract_documents import extract_documents
from src.agents.nodes.fuzzy_match import fuzzy_match
from src.agents.nodes.human_review_extraction import human_review_extraction
from src.agents.nodes.human_review_recommendation import human_review_recommendation
from src.agents.nodes.normalize import normalize
from src.agents.nodes.validate_extraction import validate_extraction
from src.agents.state import ProcurementAgentState
from src.domain.agent.analysis.normalization import NormalizationStatus

if TYPE_CHECKING:
    from src.application.evaluation.workflow import EvaluationWorkflow


class _LegacyEvaluationGraph:
    """Compatibility entrypoint for persisted evaluation workflow clients."""

    def __init__(
        self,
        workflow: EvaluationWorkflow,
        context_provider: Callable[[Mapping[str, object]], object],
        decision_model: object | None,
    ) -> None:
        self.workflow = workflow
        self.context_provider = context_provider
        self.decision_model = decision_model

    def invoke(self, state: Mapping[str, object], _config: object | None = None) -> dict[str, object]:
        result = decision_proposal(state, llm=self.decision_model)
        proposal = result.get("decision_proposal")
        if not isinstance(proposal, dict):
            return result
        evaluation = self.workflow.submit(proposal, self.context_provider(state))
        return {**result, "evaluation_result": evaluation.model_dump(mode="json")}


def begin_analysis(_: ProcurementAgentState) -> ProcurementAgentState:
    """Explicit fan-out boundary after the confirmation guard."""
    return {}


def check_data_ready(state: ProcurementAgentState) -> str:
    """Block recommendations while a quote still needs buyer confirmation."""
    for quote in state.get("normalized_quotes", []):
        match quote.status:
            case NormalizationStatus.NORMALIZED:
                continue
            case NormalizationStatus.NEEDS_MAPPING:
                return "unconfirmed"
            case unreachable:
                assert_never(unreachable)
    return "ready"


def build_graph(
    *,
    confirmed_input: bool = False,
    decision_model: DecisionModel | None = None,
    evaluation_workflow: EvaluationWorkflow | None = None,
    context_provider: Callable[[Mapping[str, object]], object] | None = None,
) -> CompiledStateGraph | _LegacyEvaluationGraph:
    """Run extraction and analysis, then pause for mandatory Buyer review."""
    if evaluation_workflow is not None:
        if context_provider is None:
            raise ValueError("context_provider is required with evaluation_workflow")
        return _LegacyEvaluationGraph(evaluation_workflow, context_provider, decision_model)
    graph = StateGraph(ProcurementAgentState)

    graph.add_node("extract_documents", extract_documents)
    graph.add_node("validate_extraction", validate_extraction)
    graph.add_node("human_review_extraction", human_review_extraction)
    graph.add_node("normalize", normalize)
    graph.add_node("fuzzy_match", fuzzy_match)
    graph.add_node("begin_analysis", begin_analysis)
    graph.add_node("calculate_tco", calculate_tco_node)
    graph.add_node("analyze_risks", analyze_risks_node)
    graph.add_node("compare_suppliers", compare_suppliers_node)
    graph.add_node(
        "decision_llm",
        decision_llm if decision_model is None else lambda state: decision_llm(state, llm=decision_model),
    )
    graph.add_node("human_review_recommendation", human_review_recommendation)
    graph.set_entry_point("normalize" if confirmed_input else "extract_documents")
    graph.add_edge("extract_documents", "validate_extraction")
    graph.add_conditional_edges(
        "validate_extraction", confidence_router, {"mandatory": "human_review_extraction", "optional": "normalize"}
    )
    graph.add_edge("human_review_extraction", "normalize")
    graph.add_edge("normalize", "fuzzy_match")
    graph.add_conditional_edges(
        "fuzzy_match",
        check_data_ready,
        {"ready": "begin_analysis", "unconfirmed": END},
    )
    # Risk analysis is independent and can execute alongside TCO. Supplier
    # comparison depends on TCO, so it must not be placed in the same fan-out.
    graph.add_edge("begin_analysis", "calculate_tco")
    graph.add_edge("begin_analysis", "analyze_risks")
    graph.add_edge("calculate_tco", "compare_suppliers")
    graph.add_edge(["compare_suppliers", "analyze_risks"], "decision_llm")
    graph.add_edge("decision_llm", "human_review_recommendation")
    graph.add_edge("human_review_recommendation", END)

    return graph.compile(checkpointer=MemorySaver())


# def build_decision_pipeline_graph() -> CompiledStateGraph:
#     """Build the standalone extraction-to-decision graph used by the legacy endpoint."""
#     graph = StateGraph(ProcurementAgentState)

#     graph.add_node("extract_documents", extract_documents)
#     graph.add_node("validate_extraction", validate_extraction)
#     graph.add_node("human_review_extraction", human_review_extraction)
#     graph.add_node("normalize", normalize)
#     graph.add_node("begin_analysis", begin_analysis)
#     graph.add_node("calculate_tco", calculate_tco_node)
#     graph.add_node("analyze_risks", analyze_risks_node)
#     graph.add_node("compare_suppliers", compare_suppliers_node)
#     graph.add_node("decision_llm", decision_llm)
#     graph.add_node("human_review_recommendation", human_review_recommendation)

#     graph.set_entry_point("extract_documents")
#     graph.add_edge("extract_documents", "validate_extraction")
#     graph.add_conditional_edges(
#         "validate_extraction",
#         confidence_router,
#         {"mandatory": "human_review_extraction", "optional": "normalize"},
#     )
#     graph.add_edge("human_review_extraction", "normalize")
#     graph.add_conditional_edges(
#         "normalize",
#         check_data_ready,
#         {"ready": "begin_analysis", "unconfirmed": END},
#     )
#     graph.add_edge("begin_analysis", "calculate_tco")
#     graph.add_edge("begin_analysis", "analyze_risks")
#     graph.add_edge("calculate_tco", "compare_suppliers")
#     graph.add_edge(["compare_suppliers", "analyze_risks"], "decision_llm")
#     graph.add_edge("decision_llm", "human_review_recommendation")
#     graph.add_edge("human_review_recommendation", END)

#     return graph.compile(checkpointer=MemorySaver())


agent = build_graph()
