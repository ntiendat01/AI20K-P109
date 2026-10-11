"""Tests for decision_llm node verifying Input/Output contracts (models_v1).

Adheres to Black-Box Boundary Testing:
- Asserts exclusively on state['decision_proposal'] and its domain contract attributes.
- Tests input preconditions, early exits, payload formatting, boundary top_n, and output decoding formats.
- LLM accuracy and hallucination checks are intentionally separated and deferred per spec.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue

from src.models_v1.analysis.comparison import (
    ComparisonCell,
    SupplierComparisonMatrix,
)
from src.models_v1.analysis.decision import (
    DecisionProposal,
    DecisionProposalStatus,
    TradeOff,
)
from src.models_v1.analysis.risk import (
    RiskFlag,
    RiskSeverity,
)
from src.models_v1.analysis.tco import (
    TCOCalculationStatus,
    TCOResult,
)


# ==============================================================================
# Isolated Node Loader
# ==============================================================================
def _load_decision_node():
    node_path = Path(__file__).resolve().parent.parent / "src" / "agents" / "nodes" / "decision_llm.py"
    module_name = "src.agents.nodes.decision_llm"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, node_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {node_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_decision_mod = _load_decision_node()
decision_llm = _decision_mod.decision_llm


# ==============================================================================
# Stub LLM Model
# ==============================================================================
class StubDecisionModel:
    def __init__(self, response: str | Mapping[str, JsonValue]) -> None:
        self.response = response
        self.call_count = 0
        self.last_messages: list[dict[str, Any]] | None = None

    def invoke(self, messages: list[dict[str, Any]]) -> str | Mapping[str, JsonValue]:
        self.call_count += 1
        self.last_messages = messages
        return self.response


# ==============================================================================
# Shared Fixtures & Helpers
# ==============================================================================
def _make_tco_result(
    supplier_id: str,
    total_tco: str | None = "10000000",
    status: TCOCalculationStatus = TCOCalculationStatus.CALCULATED,
    revision_id: str | None = None,
) -> TCOResult:
    subtotal = Decimal(total_tco) if total_tco is not None else Decimal("0.00")
    return TCOResult(
        supplier_id=supplier_id,
        quotation_revision_id=revision_id or f"rev_{supplier_id}",
        currency="VND",
        subtotal=subtotal,
        total_surcharges=Decimal("0.00"),
        total_vat=Decimal("0.00"),
        total_tco=Decimal(total_tco) if total_tco is not None else None,
        status=status,
        missing_fields=[] if status == TCOCalculationStatus.CALCULATED else ["total_tco"],
        breakdown=[],
    )


def _make_matrix(suppliers: list[str]) -> SupplierComparisonMatrix:
    return SupplierComparisonMatrix(
        suppliers=suppliers,
        criteria=["total_tco"],
        matrix={s: {"total_tco": ComparisonCell(value="10000000")} for s in suppliers},
        means={"total_tco": Decimal("10000000")},
    )


# ==============================================================================
# Nhóm 1: Kiểm soát Điều kiện Tiên quyết & Biên Đầu vào (TC-DEC-01 -> TC-DEC-08)
# ==============================================================================
def test_tc_dec_01_empty_or_missing_tco_early_exit():
    """TC-DEC-01: Không có nhà cung cấp đủ dữ liệu TCO -> NEEDS_INPUT (Không gọi LLM)."""
    stub = StubDecisionModel(response="{}")
    matrix = _make_matrix(["Alpha"])

    # Trường hợp 1: tco_results rỗng
    state_empty: dict[str, Any] = {"tco_results": [], "comparison_matrix": matrix}
    res_1 = decision_llm(state_empty, llm=stub)
    prop_1 = res_1["decision_proposal"]
    assert prop_1.status == DecisionProposalStatus.NEEDS_INPUT
    assert prop_1.preferred_supplier_id is None
    assert prop_1.ranked_supplier_ids == []
    assert prop_1.rationale == "Không có nhà cung cấp đủ dữ liệu TCO để xếp hạng."
    assert stub.call_count == 0

    # Trường hợp 2: tco_results toàn MISSING_DATA
    missing_tco = _make_tco_result("Beta", total_tco=None, status=TCOCalculationStatus.MISSING_DATA)
    state_missing: dict[str, Any] = {"tco_results": [missing_tco], "comparison_matrix": matrix}
    res_2 = decision_llm(state_missing, llm=stub)
    prop_2 = res_2["decision_proposal"]
    assert prop_2.status == DecisionProposalStatus.NEEDS_INPUT
    assert prop_2.rationale == "Không có nhà cung cấp đủ dữ liệu TCO để xếp hạng."
    assert prop_2.input_artifact_ids == [missing_tco.quotation_revision_id]
    assert stub.call_count == 0


def test_tc_dec_02_missing_comparison_matrix_early_exit():
    """TC-DEC-02: Thiếu ma trận so sánh nhà cung cấp -> NEEDS_INPUT (Không gọi LLM)."""
    stub = StubDecisionModel(response="{}")
    tco = _make_tco_result("Alpha")
    state: dict[str, Any] = {"tco_results": [tco], "comparison_matrix": None}

    res = decision_llm(state, llm=stub)
    prop = res["decision_proposal"]
    assert prop.status == DecisionProposalStatus.NEEDS_INPUT
    assert prop.preferred_supplier_id is None
    assert prop.rationale == "Thiếu ma trận so sánh nhà cung cấp."
    assert stub.call_count == 0


def test_tc_dec_03_empty_input_state():
    """TC-DEC-03: State đầu vào rỗng hoàn toàn -> Xử lý an toàn, không ném exception."""
    stub = StubDecisionModel(response="{}")
    state: dict[str, Any] = {}

    res = decision_llm(state, llm=stub)
    prop = res["decision_proposal"]
    assert prop.status == DecisionProposalStatus.NEEDS_INPUT
    assert prop.preferred_supplier_id is None
    assert prop.ranked_supplier_ids == []
    assert prop.rationale == "Không có nhà cung cấp đủ dữ liệu TCO để xếp hạng."
    assert prop.input_artifact_ids == []
    assert stub.call_count == 0


def test_tc_dec_04_unconfigured_model_provider(monkeypatch: pytest.MonkeyPatch):
    """TC-DEC-04: Chưa cấu hình mô hình quyết định (llm=None và không có API key)."""
    tco = _make_tco_result("Alpha")
    matrix = _make_matrix(["Alpha"])
    state: dict[str, Any] = {"tco_results": [tco], "comparison_matrix": matrix}

    # Giả lập settings rỗng toàn bộ API key
    fake_settings = MagicMock()
    fake_settings.openrouter_api_key = ""
    fake_settings.groq_api_key = ""
    fake_settings.qwen_base_url = ""
    fake_settings.openai_api_key = ""
    fake_settings.llm_provider = "openrouter"
    monkeypatch.setattr(_decision_mod, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(_decision_mod, "resolve_llm_provider", lambda _: "openrouter")

    res = decision_llm(state, llm=None)
    prop = res["decision_proposal"]
    assert prop.status == DecisionProposalStatus.NEEDS_INPUT
    assert prop.rationale == "Chưa cấu hình mô hình quyết định."


def test_tc_dec_05_filter_calculated_and_non_none_tco_only():
    """TC-DEC-05: Lọc dữ liệu đầu vào - Chỉ đưa NCC CALCULATED và có total_tco vào allowed_supplier_ids."""
    tco_1 = _make_tco_result("NCC 1", "10000000", TCOCalculationStatus.CALCULATED)
    tco_2 = _make_tco_result("NCC 2", None, TCOCalculationStatus.MISSING_DATA)
    tco_3 = _make_tco_result("NCC 3", None, TCOCalculationStatus.MISSING_DATA)
    tco_4 = _make_tco_result("NCC 4", "12000000", TCOCalculationStatus.CALCULATED)
    matrix = _make_matrix(["NCC 1", "NCC 4"])

    response_dict = {
        "status": "proposed",
        "preferred_supplier_id": "NCC 1",
        "ranked_supplier_ids": ["NCC 1", "NCC 4"],
        "rationale": "NCC 1 rẻ hơn.",
        "tradeoffs": [],
    }
    stub = StubDecisionModel(response=response_dict)
    state: dict[str, Any] = {
        "tco_results": [tco_1, tco_2, tco_3, tco_4],
        "comparison_matrix": matrix,
        "pr_data": {"top_n": 2},
    }

    res = decision_llm(state, llm=stub)
    prop = res["decision_proposal"]
    assert prop.status == DecisionProposalStatus.PROPOSED
    assert prop.preferred_supplier_id == "NCC 1"

    # Kiểm tra payload gửi tới LLM chỉ có NCC 1 và NCC 4
    assert stub.last_messages is not None
    assert "rationale and every tradeoffs[].description in Vietnamese" in stub.last_messages[0]["content"]
    user_payload = json.loads(stub.last_messages[1]["content"])
    assert user_payload["allowed_supplier_ids"] == ["NCC 1", "NCC 4"]


def test_tc_dec_05a_supplies_display_names_and_vnd_formatting_rules_to_agent():
    """Agent sees display names for prose while retaining server-owned IDs in the contract."""
    tco_alpha = _make_tco_result("supplier-alpha", "331100000", revision_id="rev_alpha")
    tco_beta = _make_tco_result("supplier-beta", "333960000", revision_id="rev_beta")
    stub = StubDecisionModel(
        response={
            "status": "proposed",
            "preferred_supplier_id": "supplier-alpha",
            "ranked_supplier_ids": ["supplier-alpha", "supplier-beta"],
            "rationale": "Ưu tiên chi phí đã đối chiếu.",
            "tradeoffs": [],
        }
    )
    state: dict[str, Any] = {
        "tco_results": [tco_alpha, tco_beta],
        "comparison_matrix": _make_matrix(["supplier-alpha", "supplier-beta"]),
        "confirmed_supplier_ids": ["supplier-alpha", "supplier-beta"],
        "confirmed_quotes": [
            SimpleNamespace(supplier_name="CÔNG TY CỔ PHẦN THÉP VIỆT NHẬT"),
            SimpleNamespace(supplier_name="CÔNG TY TNHH THÉP VINA KYOEI"),
        ],
    }

    decision_llm(state, llm=stub)

    assert stub.last_messages is not None
    prompt, user_message = stub.last_messages
    payload = json.loads(user_message["content"])
    assert payload["supplier_names"] == {
        "supplier-alpha": "CÔNG TY CỔ PHẦN THÉP VIỆT NHẬT",
        "supplier-beta": "CÔNG TY TNHH THÉP VINA KYOEI",
    }
    assert "supplier_names display name instead of a supplier ID or UUID" in prompt["content"]
    assert "331.100.000 VND" in prompt["content"]


def test_tc_dec_06_deduplication_of_suppliers_and_artifact_ids():
    """TC-DEC-06: Khử trùng lặp đầu vào - Nhiều dòng từ cùng NCC hoặc cùng revision_id."""
    tco_1 = _make_tco_result("Alpha", "5000000", revision_id="rev_1")
    tco_2 = _make_tco_result("Alpha", "5000000", revision_id="rev_1")  # Trùng cả NCC lẫn revision
    tco_3 = _make_tco_result("Beta", "6000000", revision_id="rev_2")
    matrix = _make_matrix(["Alpha", "Beta"])

    stub = StubDecisionModel(
        response={
            "status": "proposed",
            "preferred_supplier_id": "Alpha",
            "ranked_supplier_ids": ["Alpha", "Beta"],
            "rationale": "Chon Alpha.",
            "tradeoffs": [],
        }
    )
    state: dict[str, Any] = {"tco_results": [tco_1, tco_2, tco_3], "comparison_matrix": matrix}

    res = decision_llm(state, llm=stub)
    prop = res["decision_proposal"]
    assert prop.status == DecisionProposalStatus.PROPOSED
    assert prop.input_artifact_ids == ["rev_1", "rev_2"]

    assert stub.last_messages is not None
    user_payload = json.loads(stub.last_messages[1]["content"])
    assert user_payload["allowed_supplier_ids"] == ["Alpha", "Beta"]
    assert user_payload["input_artifact_ids"] == ["rev_1", "rev_2"]


def test_tc_dec_07_missing_or_empty_risk_flags():
    """TC-DEC-07: Khuyết thiếu hoặc rỗng cờ rủi ro -> Node gửi [] an toàn."""
    tco_1 = _make_tco_result("Alpha")
    tco_2 = _make_tco_result("Beta")
    matrix = _make_matrix(["Alpha", "Beta"])
    stub = StubDecisionModel(
        response={
            "status": "proposed",
            "preferred_supplier_id": "Alpha",
            "ranked_supplier_ids": ["Alpha", "Beta"],
            "rationale": "Chon Alpha.",
            "tradeoffs": [],
        }
    )

    # State không có key risk_flags
    state_no_risk: dict[str, Any] = {"tco_results": [tco_1, tco_2], "comparison_matrix": matrix}
    res = decision_llm(state_no_risk, llm=stub)
    assert res["decision_proposal"].status == DecisionProposalStatus.PROPOSED
    assert stub.last_messages is not None
    payload = json.loads(stub.last_messages[1]["content"])
    assert payload["risk_flags"] == []


def test_tc_dec_08_missing_or_empty_pr_data_defaults_top_n():
    """TC-DEC-08: Khuyết thiếu hoặc rỗng pr_data -> Mặc định top_n = 3."""
    tco = [_make_tco_result(f"NCC_{i}") for i in range(4)]
    matrix = _make_matrix([f"NCC_{i}" for i in range(4)])
    stub = StubDecisionModel(
        response={
            "status": "proposed",
            "preferred_supplier_id": "NCC_0",
            "ranked_supplier_ids": ["NCC_0", "NCC_1", "NCC_2"],
            "rationale": "Chon 0.",
            "tradeoffs": [],
        }
    )

    # Không có pr_data trong state
    state: dict[str, Any] = {"tco_results": tco, "comparison_matrix": matrix}
    res = decision_llm(state, llm=stub)
    assert res["decision_proposal"].status == DecisionProposalStatus.PROPOSED

    assert stub.last_messages is not None
    payload = json.loads(stub.last_messages[1]["content"])
    assert payload["top_n"] == 3


# ==============================================================================
# Nhóm 2: Kiểm chứng Hợp đồng Cấu trúc Prompt Payload Gửi LLM (TC-DEC-09 -> TC-DEC-10)
# ==============================================================================
def test_tc_dec_09_prompt_payload_contract_seven_fields():
    """TC-DEC-09: Cấu trúc Prompt Payload gồm đúng 2 messages và đủ 7 trường bắt buộc."""
    tco_1 = _make_tco_result("Alpha", "10000000", revision_id="rev_a")
    tco_2 = _make_tco_result("Beta", "12000000", revision_id="rev_b")
    matrix = _make_matrix(["Alpha", "Beta"])
    risk = RiskFlag(
        risk_type="lead_time_exceeded",
        severity=RiskSeverity.HIGH,
        supplier_id="Beta",
        description="Thời gian giao hàng vượt hạn chót PR",
        details={"delta": 5},
    )

    stub = StubDecisionModel(
        response={
            "status": "proposed",
            "preferred_supplier_id": "Alpha",
            "ranked_supplier_ids": ["Alpha", "Beta"],
            "rationale": "Tot.",
            "tradeoffs": [],
        }
    )
    state: dict[str, Any] = {
        "tco_results": [tco_1, tco_2],
        "comparison_matrix": matrix,
        "risk_flags": [risk],
        "pr_data": {"top_n": 2},
    }

    decision_llm(state, llm=stub)

    assert stub.last_messages is not None
    assert len(stub.last_messages) == 2
    sys_msg, user_msg = stub.last_messages

    assert sys_msg["role"] == "system"
    assert isinstance(sys_msg["content"], str) and len(sys_msg["content"]) > 0

    assert user_msg["role"] == "user"
    payload = json.loads(user_msg["content"])

    required_keys = {
        "schema",
        "allowed_supplier_ids",
        "top_n",
        "tco_results",
        "comparison_matrix",
        "risk_flags",
        "supplier_names",
        "input_artifact_ids",
    }
    assert required_keys.issubset(payload.keys())
    assert payload["allowed_supplier_ids"] == ["Alpha", "Beta"]
    assert payload["top_n"] == 2
    assert len(payload["tco_results"]) == 2
    assert len(payload["risk_flags"]) == 1
    assert payload["risk_flags"][0]["supplier_id"] == "Beta"
    assert payload["input_artifact_ids"] == ["rev_a", "rev_b"]


def test_tc_dec_10_top_n_boundary_configuration():
    """TC-DEC-10: Cấu hình top_n biên - Mặc định, trong dải 1..5, ngoài dải, boolean, string."""
    tco = [_make_tco_result(f"NCC_{i}") for i in range(5)]
    matrix = _make_matrix([f"NCC_{i}" for i in range(5)])

    cases = [
        ({"top_n": 2}, 2),  # Trong dải 1..5
        ({"top_n": 1}, 1),  # Cận dưới
        ({"top_n": 5}, 5),  # Cận trên
        ({"top_n": 0}, 3),  # < MIN_TOP_N -> fallback 3
        ({"top_n": -1}, 3),  # Số âm -> fallback 3
        ({"top_n": 10}, 3),  # > MAX_TOP_N -> fallback 3
        ({"top_n": True}, 3),  # Boolean -> fallback 3
        ({"top_n": "2"}, 3),  # String -> fallback 3
    ]

    for pr_data, expected_top_n in cases:
        stub = StubDecisionModel(
            response={
                "status": "needs_input",
                "rationale": "Testing top_n boundary.",
                "tradeoffs": [],
            }
        )
        state: dict[str, Any] = {
            "tco_results": tco,
            "comparison_matrix": matrix,
            "pr_data": pr_data,
        }
        decision_llm(state, llm=stub)
        assert stub.last_messages is not None
        payload = json.loads(stub.last_messages[1]["content"])
        assert payload["top_n"] == expected_top_n, f"Failed for {pr_data}"


# ==============================================================================
# Nhóm 3: Các Kịch bản Happy Path Input - Output Chuẩn (TC-DEC-11 -> TC-DEC-16)
# ==============================================================================
def test_tc_dec_11_happy_path_two_suppliers_proposed():
    """TC-DEC-11: Happy Path cơ bản - Đề xuất thành công 2 NCC kèm TradeOff."""
    tco_1 = _make_tco_result("Công ty Alpha", "10000000", revision_id="rev_alpha")
    tco_2 = _make_tco_result("Công ty Beta", "12000000", revision_id="rev_beta")
    matrix = _make_matrix(["Công ty Alpha", "Công ty Beta"])

    stub = StubDecisionModel(
        response={
            "status": "proposed",
            "preferred_supplier_id": "Công ty Alpha",
            "ranked_supplier_ids": ["Công ty Alpha", "Công ty Beta"],
            "rationale": "Công ty Alpha có TCO thấp nhất và thời gian giao hàng nhanh nhất.",
            "tradeoffs": [
                {
                    "preferred_supplier_id": "Công ty Alpha",
                    "alternative_supplier_id": "Công ty Beta",
                    "description": "Alpha rẻ hơn 2 triệu VND và giao nhanh hơn 5 ngày.",
                }
            ],
            "input_artifact_ids": [],
        }
    )
    state: dict[str, Any] = {
        "tco_results": [tco_1, tco_2],
        "comparison_matrix": matrix,
        "pr_data": {"top_n": 2},
    }

    res = decision_llm(state, llm=stub)
    prop = res["decision_proposal"]
    assert prop.status == DecisionProposalStatus.PROPOSED
    assert prop.preferred_supplier_id == "Công ty Alpha"
    assert prop.ranked_supplier_ids == ["Công ty Alpha", "Công ty Beta"]
    assert len(prop.tradeoffs) == 1
    assert prop.tradeoffs[0].preferred_supplier_id == "Công ty Alpha"
    assert prop.tradeoffs[0].alternative_supplier_id == "Công ty Beta"
    assert prop.input_artifact_ids == ["rev_alpha", "rev_beta"]


def test_tc_dec_12_happy_path_three_suppliers_top_3():
    """TC-DEC-12: Happy Path đa nhà cung cấp - Xếp hạng đủ 3 NCC (top_n = 3)."""
    tco = [_make_tco_result(name) for name in ["Alpha", "Beta", "Gamma"]]
    matrix = _make_matrix(["Alpha", "Beta", "Gamma"])

    stub = StubDecisionModel(
        response={
            "status": "proposed",
            "preferred_supplier_id": "Alpha",
            "ranked_supplier_ids": ["Alpha", "Beta", "Gamma"],
            "rationale": "Alpha tot nhat.",
            "tradeoffs": [],
        }
    )
    state: dict[str, Any] = {
        "tco_results": tco,
        "comparison_matrix": matrix,
        "pr_data": {"top_n": 3},
    }

    res = decision_llm(state, llm=stub)
    prop = res["decision_proposal"]
    assert prop.status == DecisionProposalStatus.PROPOSED
    assert len(prop.ranked_supplier_ids) == 3
    assert prop.ranked_supplier_ids == ["Alpha", "Beta", "Gamma"]


def test_tc_dec_13_happy_path_top_1_single_supplier():
    """TC-DEC-13: Happy Path giới hạn - Yêu cầu top_n = 1 (Chỉ chọn 1 NCC duy nhất)."""
    tco = [_make_tco_result("Alpha"), _make_tco_result("Beta")]
    matrix = _make_matrix(["Alpha", "Beta"])

    stub = StubDecisionModel(
        response={
            "status": "proposed",
            "preferred_supplier_id": "Alpha",
            "ranked_supplier_ids": ["Alpha"],
            "rationale": "Chon duy nhat Alpha.",
            "tradeoffs": [],
        }
    )
    state: dict[str, Any] = {
        "tco_results": tco,
        "comparison_matrix": matrix,
        "pr_data": {"top_n": 1},
    }

    res = decision_llm(state, llm=stub)
    prop = res["decision_proposal"]
    assert prop.status == DecisionProposalStatus.PROPOSED
    assert len(prop.ranked_supplier_ids) == 1
    assert prop.ranked_supplier_ids == ["Alpha"]


def test_tc_dec_14_clamp_ranking_count_when_top_n_exceeds_available():
    """TC-DEC-14: Kẹp số lượng xếp hạng - Yêu cầu top_n = 5 nhưng chỉ có 2 NCC."""
    tco = [_make_tco_result("Alpha"), _make_tco_result("Beta")]
    matrix = _make_matrix(["Alpha", "Beta"])

    stub = StubDecisionModel(
        response={
            "status": "proposed",
            "preferred_supplier_id": "Alpha",
            "ranked_supplier_ids": ["Alpha", "Beta"],
            "rationale": "Chi co 2 NCC.",
            "tradeoffs": [],
        }
    )
    state: dict[str, Any] = {
        "tco_results": tco,
        "comparison_matrix": matrix,
        "pr_data": {"top_n": 5},
    }

    res = decision_llm(state, llm=stub)
    prop = res["decision_proposal"]
    assert prop.status == DecisionProposalStatus.PROPOSED
    assert len(prop.ranked_supplier_ids) == 2


def test_tc_dec_15_risk_flags_integration_in_decision():
    """TC-DEC-15: Tích hợp rủi ro - Truyền và phản ánh cờ rủi ro vào quyết định."""
    tco = [_make_tco_result("Alpha"), _make_tco_result("Beta")]
    matrix = _make_matrix(["Alpha", "Beta"])
    risk = RiskFlag(
        risk_type="lead_time_exceeded",
        severity=RiskSeverity.HIGH,
        supplier_id="Beta",
        description="Thời gian giao hàng vượt hạn chót PR",
        details={"delta": 10},
    )

    stub = StubDecisionModel(
        response={
            "status": "proposed",
            "preferred_supplier_id": "Alpha",
            "ranked_supplier_ids": ["Alpha", "Beta"],
            "rationale": "Chon Alpha vi Beta co rui ro giao tre 10 ngay.",
            "tradeoffs": [],
        }
    )
    state: dict[str, Any] = {
        "tco_results": tco,
        "comparison_matrix": matrix,
        "risk_flags": [risk],
        "pr_data": {"top_n": 2},
    }

    res = decision_llm(state, llm=stub)
    prop = res["decision_proposal"]
    assert prop.status == DecisionProposalStatus.PROPOSED
    assert prop.preferred_supplier_id == "Alpha"
    assert "Beta" in prop.rationale


def test_tc_dec_16_llm_proactively_requests_needs_input():
    """TC-DEC-16: LLM chủ động yêu cầu ý kiến Buyer (status = NEEDS_INPUT)."""
    tco = [_make_tco_result("Alpha"), _make_tco_result("Beta")]
    matrix = _make_matrix(["Alpha", "Beta"])

    stub = StubDecisionModel(
        response={
            "status": "needs_input",
            "rationale": "Ca hai NCC deu tre han > 15 ngay so voi deadline PR. Can Buyer xac nhan.",
            "input_artifact_ids": [],
        }
    )
    state: dict[str, Any] = {"tco_results": tco, "comparison_matrix": matrix}

    res = decision_llm(state, llm=stub)
    prop = res["decision_proposal"]
    assert prop.status == DecisionProposalStatus.NEEDS_INPUT
    assert prop.preferred_supplier_id is None
    assert prop.ranked_supplier_ids == []
    assert "Can Buyer xac nhan" in prop.rationale
    assert prop.input_artifact_ids == [r.quotation_revision_id for r in tco]


# ==============================================================================
# Nhóm 4: Hợp đồng Định dạng & Khử nhiễu Đầu ra (TC-DEC-17 -> TC-DEC-23)
# ==============================================================================
def test_tc_dec_17_output_format_plain_json_string():
    """TC-DEC-17: Định dạng Output - LLM trả về chuỗi JSON thuần (str)."""
    tco = [_make_tco_result("Alpha"), _make_tco_result("Beta")]
    matrix = _make_matrix(["Alpha", "Beta"])
    raw_json = json.dumps(
        {
            "status": "proposed",
            "preferred_supplier_id": "Alpha",
            "ranked_supplier_ids": ["Alpha", "Beta"],
            "rationale": "Chuoi JSON thuan hop le.",
            "tradeoffs": [],
        }
    )
    stub = StubDecisionModel(response=raw_json)
    state: dict[str, Any] = {"tco_results": tco, "comparison_matrix": matrix, "pr_data": {"top_n": 2}}

    res = decision_llm(state, llm=stub)
    assert res["decision_proposal"].status == DecisionProposalStatus.PROPOSED
    assert res["decision_proposal"].preferred_supplier_id == "Alpha"


def test_tc_dec_18_output_format_python_mapping():
    """TC-DEC-18: Định dạng Output - LLM trả về Python Dictionary (Mapping)."""
    tco = [_make_tco_result("Alpha"), _make_tco_result("Beta")]
    matrix = _make_matrix(["Alpha", "Beta"])
    raw_dict = {
        "status": "proposed",
        "preferred_supplier_id": "Alpha",
        "ranked_supplier_ids": ["Alpha", "Beta"],
        "rationale": "Dict truc tiep.",
        "tradeoffs": [],
    }
    stub = StubDecisionModel(response=raw_dict)
    state: dict[str, Any] = {"tco_results": tco, "comparison_matrix": matrix, "pr_data": {"top_n": 2}}

    res = decision_llm(state, llm=stub)
    assert res["decision_proposal"].status == DecisionProposalStatus.PROPOSED
    assert res["decision_proposal"].preferred_supplier_id == "Alpha"


def test_tc_dec_19_output_format_markdown_fence_with_json_tag():
    """TC-DEC-19: Định dạng Output - LLM bọc JSON trong Markdown Code Block có tag ```json."""
    tco = [_make_tco_result("Alpha"), _make_tco_result("Beta")]
    matrix = _make_matrix(["Alpha", "Beta"])
    fence_text = (
        "```json\n"
        "{\n"
        '  "status": "proposed",\n'
        '  "preferred_supplier_id": "Alpha",\n'
        '  "ranked_supplier_ids": ["Alpha", "Beta"],\n'
        '  "rationale": "Fence with json tag.",\n'
        '  "tradeoffs": []\n'
        "}\n"
        "```"
    )
    stub = StubDecisionModel(response=fence_text)
    state: dict[str, Any] = {"tco_results": tco, "comparison_matrix": matrix, "pr_data": {"top_n": 2}}

    res = decision_llm(state, llm=stub)
    assert res["decision_proposal"].status == DecisionProposalStatus.PROPOSED
    assert res["decision_proposal"].preferred_supplier_id == "Alpha"


def test_tc_dec_20_output_format_markdown_fence_without_tag():
    """TC-DEC-20: Định dạng Output - LLM bọc JSON trong Markdown Code Block không tag ```."""
    tco = [_make_tco_result("Alpha"), _make_tco_result("Beta")]
    matrix = _make_matrix(["Alpha", "Beta"])
    fence_text = (
        "```\n"
        "{\n"
        '  "status": "proposed",\n'
        '  "preferred_supplier_id": "Alpha",\n'
        '  "ranked_supplier_ids": ["Alpha", "Beta"],\n'
        '  "rationale": "Fence without tag.",\n'
        '  "tradeoffs": []\n'
        "}\n"
        "```"
    )
    stub = StubDecisionModel(response=fence_text)
    state: dict[str, Any] = {"tco_results": tco, "comparison_matrix": matrix, "pr_data": {"top_n": 2}}

    res = decision_llm(state, llm=stub)
    assert res["decision_proposal"].status == DecisionProposalStatus.PROPOSED
    assert res["decision_proposal"].preferred_supplier_id == "Alpha"


def test_tc_dec_21_output_format_whitespace_and_newline_tolerance():
    """TC-DEC-21: Định dạng Output - Chuỗi JSON chứa khoảng trắng và dòng trống đầu/cuối."""
    tco = [_make_tco_result("Alpha"), _make_tco_result("Beta")]
    matrix = _make_matrix(["Alpha", "Beta"])
    dirty_text = (
        "\n\n   \t  "
        '{"status": "proposed", "preferred_supplier_id": "Alpha", "ranked_supplier_ids": ["Alpha", "Beta"], "rationale": "Tot.", "tradeoffs": []}'
        "   \n\t\n  "
    )
    stub = StubDecisionModel(response=dirty_text)
    state: dict[str, Any] = {"tco_results": tco, "comparison_matrix": matrix, "pr_data": {"top_n": 2}}

    res = decision_llm(state, llm=stub)
    assert res["decision_proposal"].status == DecisionProposalStatus.PROPOSED
    assert res["decision_proposal"].preferred_supplier_id == "Alpha"


def test_tc_dec_22_output_artifact_ids_enforcement():
    """TC-DEC-22: Chuẩn hóa bắt buộc input_artifact_ids - Node tự động ghi đè revision IDs chuẩn."""
    tco_1 = _make_tco_result("Alpha", revision_id="real_rev_01")
    tco_2 = _make_tco_result("Beta", revision_id="real_rev_02")
    matrix = _make_matrix(["Alpha", "Beta"])

    # LLM trả về proposal cố tình chứa artifact_id lạ
    stub = StubDecisionModel(
        response={
            "status": "proposed",
            "preferred_supplier_id": "Alpha",
            "ranked_supplier_ids": ["Alpha", "Beta"],
            "rationale": "Ghi de artifact.",
            "tradeoffs": [],
            "input_artifact_ids": ["bogus_artifact_999", "fake_id"],
        }
    )
    state: dict[str, Any] = {
        "tco_results": [tco_1, tco_2],
        "comparison_matrix": matrix,
        "pr_data": {"top_n": 2},
    }

    res = decision_llm(state, llm=stub)
    prop = res["decision_proposal"]
    assert prop.status == DecisionProposalStatus.PROPOSED
    # Bị ghi đè bằng đúng danh sách revision thật từ tco_results
    assert prop.input_artifact_ids == ["real_rev_01", "real_rev_02"]
    assert "bogus_artifact_999" not in prop.input_artifact_ids


def test_tc_dec_23_output_schema_integrity():
    """TC-DEC-23: Kiểm chứng tính toàn vẹn Schema đầu ra của DecisionProposal."""
    tco = [_make_tco_result("Alpha"), _make_tco_result("Beta")]
    matrix = _make_matrix(["Alpha", "Beta"])
    stub = StubDecisionModel(
        response={
            "status": "proposed",
            "preferred_supplier_id": "Alpha",
            "ranked_supplier_ids": ["Alpha", "Beta"],
            "rationale": "Schema test.",
            "tradeoffs": [
                {
                    "preferred_supplier_id": "Alpha",
                    "alternative_supplier_id": "Beta",
                    "description": "Chi tiet trade-off.",
                }
            ],
        }
    )
    state: dict[str, Any] = {"tco_results": tco, "comparison_matrix": matrix, "pr_data": {"top_n": 2}}

    out = decision_llm(state, llm=stub)
    assert set(out.keys()) == {"decision_proposal"}
    prop = out["decision_proposal"]
    assert isinstance(prop, DecisionProposal)
    assert isinstance(prop.status, DecisionProposalStatus)
    assert isinstance(prop.preferred_supplier_id, str)
    assert isinstance(prop.ranked_supplier_ids, list)
    assert isinstance(prop.rationale, str)
    assert isinstance(prop.tradeoffs, list)
    assert isinstance(prop.tradeoffs[0], TradeOff)
    assert isinstance(prop.input_artifact_ids, list)
