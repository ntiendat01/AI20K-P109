from __future__ import annotations

from typing import Literal

from src.agents.state import ProcurementAgentState


def confidence_router(
    state: ProcurementAgentState,
) -> Literal["mandatory", "optional"]:
    """Route mandatory reviews to HITL and optional reviews to normalization."""
    return state.get("review_mode", "mandatory")
