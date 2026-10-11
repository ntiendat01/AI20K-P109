from __future__ import annotations

from src.agents.state import ProcurementAgentState


def process_feedback(state: ProcurementAgentState) -> ProcurementAgentState:
    """Append buyer feedback and count the revision before re-analysis."""
    recommendation = dict(state.get("recommendation", {}))
    recommendation["feedback_processed"] = True
    history_value = recommendation.get("feedback_history", [])
    history = [entry for entry in history_value if isinstance(entry, str)] if isinstance(history_value, list) else []
    note = state.get("human_feedback", {}).get("note")
    if isinstance(note, str):
        history.append(note)
    recommendation["feedback_history"] = history

    revise_count = state.get("revise_count", 0)
    if not isinstance(revise_count, int) or isinstance(revise_count, bool):
        revise_count = 0
    return {
        "recommendation": recommendation,
        "revise_count": revise_count + 1,
    }
