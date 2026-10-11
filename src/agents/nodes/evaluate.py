from __future__ import annotations

from src.agents.state import ProcurementAgentState


def evaluate(state: ProcurementAgentState) -> ProcurementAgentState:
    """Create deterministic evaluation data used by the sufficiency router."""
    # TCO và Risk Evaluation đã được gộp vào decision_llm (trong _with_decision_context)
    # Node này giờ chỉ còn là trạm trung chuyển (pass-through) để đi tới evaluate_sufficiency
    return {}


def evaluate_sufficiency(state: ProcurementAgentState) -> str:
    """Continue only when at least two quote evaluations are available."""
    if len(state.get("tco_results", [])) >= 2:
        return "sufficient"
    return "insufficient"
