"""P3 prompt compaction keeps the evaluation-facing facts intact."""

from __future__ import annotations

import pytest

from src.agents.nodes.decision_llm import (
    build_decision_payload,
    build_legacy_decision_payload,
    estimate_payload_tokens,
)


def sample_state(suppliers: int) -> dict[str, object]:
    ids = [f"supplier-{index}" for index in range(suppliers)]
    facts = [
        {
            "supplier_id": supplier,
            "metric": metric,
            "value": value,
            "unit": unit,
            "time_origin": origin,
            "conditions": [],
        }
        for index, supplier in enumerate(ids)
        for metric, value, unit, origin in [
            ("tco", 1_000_000 + index * 10_000, "VND", None),
            ("delivery_days", 5 + index, "calendar_day", "order_confirmation"),
            ("warranty_months", 12 + index, "month", None),
        ]
    ]
    tco = [
        {
            "supplier_id": supplier,
            "items_tco": [
                {
                    "item_name": "Steel component",
                    "quantity": 100,
                    "unit_price": 10000 + index,
                    "subtotal": 1000000 + index,
                    "surcharges": 5000,
                    "vat_rate": 0.1,
                    "vat_included": False,
                    "item_tco": 1105500 + index,
                }
            ],
            "subtotal": 1000000 + index,
            "total_surcharges": 5000,
            "total_vat": 100500,
            "total_tco": 1105500 + index,
            "status": "calculated",
            "missing_fields": [],
        }
        for index, supplier in enumerate(ids)
    ]
    matrix = {
        "suppliers": ids,
        "criteria": ["total_tco", "lead_time_days", "warranty_months"],
        "matrix": {
            supplier: {
                "total_tco": {"value": 1105500 + index, "deviation_pct": 1.0, "highlight": False, "note": None},
                "lead_time_days": {"value": 5 + index, "deviation_pct": 1.0, "highlight": False, "note": None},
                "warranty_months": {"value": 12 + index, "deviation_pct": 1.0, "highlight": False, "note": None},
            }
            for index, supplier in enumerate(ids)
        },
        "means": {"total_tco": 0, "lead_time_days": 0, "warranty_months": 0},
        "deviation_threshold": 0.15,
    }
    return {
        "pr_data": {"top_n": 3},
        "tco_results": tco,
        "comparison_matrix": matrix,
        "decision_context": {
            "candidate_ids": ids,
            "facts": facts,
            "constraints": [],
            "mandatory_comparisons": ["tco", "delivery_days", "warranty_months"],
        },
    }


@pytest.mark.parametrize("count", [2, 5, 10])
def test_compact_payload_retains_claimable_values_and_reduces_tokens(count):
    state = sample_state(count)
    old = build_legacy_decision_payload(state, [])
    compact = build_decision_payload(state, [])

    assert set(compact) == {
        "schema",
        "top_n",
        "tco_results",
        "comparison_matrix",
        "risk_flags",
        "confirmed_context",
    }
    assert "$defs" in compact["schema"]
    assert compact["schema"]["required"] == [
        "decision",
        "recommendation",
        "claims",
        "comparisons",
        "trade_offs",
        "negotiation_points",
        "risk_flags",
        "uncertainties",
        "open_questions",
        "assumptions",
    ]
    compact_facts = compact["confirmed_context"]["facts"]
    assert [(fact["supplier_id"], fact["metric"], fact["value"], fact["unit"]) for fact in compact_facts] == [
        (fact["supplier_id"], fact["metric"], fact["value"], fact["unit"])
        for fact in state["decision_context"]["facts"]
    ]
    assert all(
        fact.get("time_origin") == "order_confirmation" for fact in compact_facts if fact["metric"] == "delivery_days"
    )
    assert all("items_tco" not in result for result in compact["tco_results"])
    assert all(
        set(cell) == {"value"} for row in compact["comparison_matrix"]["matrix"].values() for cell in row.values()
    )
    assert estimate_payload_tokens(compact) < estimate_payload_tokens(old)
