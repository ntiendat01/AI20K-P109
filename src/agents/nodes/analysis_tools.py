"""Deterministic analysis nodes used before the decision LLM.

These nodes deliberately contain no model calls.  Keeping them separate makes
the graph dependencies explicit and allows each result to be tested, retried,
or replaced without invoking the decision model.
"""

from __future__ import annotations

from datetime import date

from src.agents.state import ProcurementAgentState
from src.agents.tools.analyze_risks import analyze_risks
from src.agents.tools.calculate_tco import calculate_tco
from src.agents.tools.compare_suppliers import compare_suppliers


def calculate_tco_node(state: ProcurementAgentState) -> ProcurementAgentState:
    """Calculate TCO from buyer-confirmed, normalized quotations."""
    target_currency = str(state.get("pr_data", {}).get("target_currency", "VND"))
    return {
        "tco_results": calculate_tco(
            state.get("normalized_quotes", []),
            state.get("confirmed_quotes", []),
            target_currency,
            supplier_ids=state.get("confirmed_supplier_ids"),
        )
    }


def analyze_risks_node(state: ProcurementAgentState) -> ProcurementAgentState:
    """Analyze non-financial risks independently from TCO calculation."""
    pr_data = state.get("pr_data", {})
    deadline_value = pr_data.get("delivery_due_date") or pr_data.get("deadline")
    delivery_due_date = date.fromisoformat(str(deadline_value)) if deadline_value is not None else None
    return {
        "risk_flags": analyze_risks(
            state.get("normalized_quotes", []),
            state.get("confirmed_quotes", []),
            delivery_due_date,
            supplier_ids=state.get("confirmed_supplier_ids"),
        )
    }


def compare_suppliers_node(state: ProcurementAgentState) -> ProcurementAgentState:
    """Build the comparison matrix after TCO is available."""
    return {
        "comparison_matrix": compare_suppliers(
            state.get("normalized_quotes", []),
            state.get("confirmed_quotes", []),
            state.get("tco_results", []),
            supplier_ids=state.get("confirmed_supplier_ids"),
        )
    }
