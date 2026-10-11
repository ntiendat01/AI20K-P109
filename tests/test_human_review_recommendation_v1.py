"""Tests for human_review_recommendation node and buyer_decision_router (HITL-2, models_v1).

Adheres to Black-Box Boundary Testing:
- Asserts exclusively on state['buyer_approval_request'] and router return string.
- Mocks only the LangGraph interrupt function to simulate Buyer UI responses.
- Enforces strict compliance with tasks/test_agent_plan/TC-human_review_recommendation.md.
"""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.models_v1.analysis.comparison import (
    ComparisonCell,
    SupplierComparisonMatrix,
)
from src.models_v1.analysis.decision import (
    DecisionProposal,
    DecisionProposalStatus,
    TradeOff,
)
from src.models_v1.approval import (
    BuyerAction,
    BuyerSubmitApprovalRequest,
)


# ==============================================================================
# Isolated Node Loader
# ==============================================================================
def _load_hrr_module():
    node_path = Path(__file__).resolve().parent.parent / "src" / "agents" / "nodes" / "human_review_recommendation.py"
    module_name = "src.agents.nodes.human_review_recommendation"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, node_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {node_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_hrr_mod = _load_hrr_module()
human_review_recommendation = _hrr_mod.human_review_recommendation
buyer_decision_router = _hrr_mod.buyer_decision_router
AnalysisRevisionMismatchError = _hrr_mod.AnalysisRevisionMismatchError


# ==============================================================================
# Helpers & Fixtures
# ==============================================================================
def _make_proposal(preferred: str = "Alpha") -> DecisionProposal:
    return DecisionProposal(
        status=DecisionProposalStatus.PROPOSED,
        preferred_supplier_id=preferred,
        ranked_supplier_ids=[preferred, "Beta"],
        rationale=f"Lựa chọn {preferred} tối ưu.",
        tradeoffs=[
            TradeOff(
                preferred_supplier_id=preferred,
                alternative_supplier_id="Beta",
                description="TCO thấp hơn.",
            )
        ],
        input_artifact_ids=["rev-1", "rev-2"],
    )


def _make_matrix() -> SupplierComparisonMatrix:
    return SupplierComparisonMatrix(
        suppliers=["Alpha", "Beta"],
        criteria=["total_tco"],
        matrix={
            "Alpha": {"total_tco": ComparisonCell(value="10000000")},
            "Beta": {"total_tco": ComparisonCell(value="12000000")},
        },
        means={"total_tco": Decimal("11000000")},
    )


def _make_state(
    analysis_revision: int = 1,
    revise_count: int = 0,
) -> dict[str, Any]:
    return {
        "decision_proposal": _make_proposal(),
        "comparison_matrix": _make_matrix(),
        "analysis_revision": analysis_revision,
        "revise_count": revise_count,
    }


# ==============================================================================
# Nhóm 1: Node human_review_recommendation (HITL-2 Boundary)
# ==============================================================================
def test_tc_hrr_01_submit_action_with_note(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-HRR-01: Happy Path - Buyer duyệt đề xuất (SUBMIT) kèm ghi chú."""
    buyer_response = {
        "analysis_revision": 1,
        "action": "submit",
        "note": "Đồng ý đề xuất chọn NCC Alpha vì giá tốt nhất.",
    }
    monkeypatch.setattr(_hrr_mod, "interrupt", MagicMock(return_value=buyer_response))

    state = _make_state(analysis_revision=1)
    result = human_review_recommendation(state)

    assert "buyer_approval_request" in result
    req = result["buyer_approval_request"]
    assert isinstance(req, BuyerSubmitApprovalRequest)
    assert req.action == BuyerAction.SUBMIT
    assert req.analysis_revision == 1
    assert req.note == "Đồng ý đề xuất chọn NCC Alpha vì giá tốt nhất."


def test_tc_hrr_02_submit_action_without_note(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-HRR-02: Happy Path - Buyer duyệt đề xuất (SUBMIT) không kèm ghi chú."""
    buyer_response = {
        "analysis_revision": 1,
        "action": "submit",
    }
    monkeypatch.setattr(_hrr_mod, "interrupt", MagicMock(return_value=buyer_response))

    state = _make_state(analysis_revision=1)
    result = human_review_recommendation(state)

    req = result["buyer_approval_request"]
    assert req.action == BuyerAction.SUBMIT
    assert req.note is None


def test_tc_hrr_03_revise_action_with_required_note(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-HRR-03: Happy Path - Buyer yêu cầu điều chỉnh (REVISE) kèm ghi chú bắt buộc."""
    buyer_response = {
        "analysis_revision": 1,
        "action": "revise",
        "note": "Yêu cầu đàm phán lại tiến độ giao hàng với NCC Beta do thời hạn gấp.",
    }
    monkeypatch.setattr(_hrr_mod, "interrupt", MagicMock(return_value=buyer_response))

    state = _make_state(analysis_revision=1)
    result = human_review_recommendation(state)

    req = result["buyer_approval_request"]
    assert req.action == BuyerAction.REVISE
    assert req.note == "Yêu cầu đàm phán lại tiến độ giao hàng với NCC Beta do thời hạn gấp."


def test_tc_hrr_04_revise_action_missing_note_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-HRR-04: Bắt buộc Ghi chú khi Yêu cầu Chỉnh sửa (action=REVISE thiếu note)."""
    # Trường hợp 1: Thiếu trường note hoàn toàn
    buyer_response_no_note = {
        "analysis_revision": 1,
        "action": "revise",
    }
    monkeypatch.setattr(_hrr_mod, "interrupt", MagicMock(return_value=buyer_response_no_note))
    state = _make_state(analysis_revision=1)
    with pytest.raises(ValidationError) as exc_info:
        human_review_recommendation(state)
    assert "note is required when Buyer requests revision" in str(exc_info.value)

    # Trường hợp 2: note là chuỗi rỗng
    buyer_response_empty_note = {
        "analysis_revision": 1,
        "action": "revise",
        "note": "",
    }
    monkeypatch.setattr(_hrr_mod, "interrupt", MagicMock(return_value=buyer_response_empty_note))
    with pytest.raises(ValidationError) as exc_info2:
        human_review_recommendation(state)
    assert "note is required when Buyer requests revision" in str(exc_info2.value)


def test_tc_hrr_05_interrupt_payload_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-HRR-05: Kiểm tra cấu trúc Interrupt Payload gửi tới Buyer UI."""
    mock_interrupt = MagicMock(return_value={"analysis_revision": 2, "action": "submit"})
    monkeypatch.setattr(_hrr_mod, "interrupt", mock_interrupt)

    state = _make_state(analysis_revision=2, revise_count=1)
    human_review_recommendation(state)

    assert mock_interrupt.call_count == 1
    call_payload = mock_interrupt.call_args[0][0]

    assert call_payload["checkpoint"] == "recommendation_review"
    assert call_payload["analysis_revision"] == 2
    assert isinstance(call_payload["decision_proposal"], dict)
    assert call_payload["decision_proposal"]["preferred_supplier_id"] == "Alpha"
    assert isinstance(call_payload["comparison_matrix"], dict)
    assert call_payload["comparison_matrix"]["suppliers"] == ["Alpha", "Beta"]
    assert call_payload["max_revise_reached"] is False


def test_tc_hrr_06_max_revise_reached_flag_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-HRR-06: Cờ Cảnh Báo Số Lần Điều Chỉnh (max_revise_reached >= 3)."""
    mock_interrupt = MagicMock(return_value={"analysis_revision": 1, "action": "submit"})
    monkeypatch.setattr(_hrr_mod, "interrupt", mock_interrupt)

    cases = [
        (0, False),
        (1, False),
        (2, False),
        (3, True),
        (4, True),
    ]

    for count, expected_flag in cases:
        state = _make_state(analysis_revision=1, revise_count=count)
        human_review_recommendation(state)
        last_payload = mock_interrupt.call_args[0][0]
        assert last_payload["max_revise_reached"] is expected_flag, f"Failed at count={count}"


def test_tc_hrr_07_analysis_revision_mismatch_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-HRR-07: Chống Sai Lệch Phiên Phê Duyệt (AnalysisRevisionMismatchError)."""
    # State đang ở revision 2 nhưng Buyer gửi về revision 1
    buyer_response = {
        "analysis_revision": 1,
        "action": "submit",
    }
    monkeypatch.setattr(_hrr_mod, "interrupt", MagicMock(return_value=buyer_response))

    state = _make_state(analysis_revision=2)
    with pytest.raises(AnalysisRevisionMismatchError) as exc_info:
        human_review_recommendation(state)

    err = exc_info.value
    assert err.expected == 2
    assert err.actual == 1
    assert "Expected analysis revision 2, received 1" in str(err)


def test_tc_hrr_08_default_analysis_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-HRR-08: Giá trị Mặc định cho analysis_revision (mặc định 1 khi khuyết thiếu)."""
    buyer_response = {
        "analysis_revision": 1,
        "action": "submit",
    }
    mock_interrupt = MagicMock(return_value=buyer_response)
    monkeypatch.setattr(_hrr_mod, "interrupt", mock_interrupt)

    # State không có key analysis_revision
    state = {
        "decision_proposal": _make_proposal(),
        "comparison_matrix": _make_matrix(),
    }
    result = human_review_recommendation(state)

    assert mock_interrupt.call_args[0][0]["analysis_revision"] == 1
    assert result["buyer_approval_request"].analysis_revision == 1


def test_tc_hrr_09_invalid_buyer_payload_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-HRR-09: Buyer Trả Về Dữ Liệu Lỗi Cú Pháp hoặc Sai Schema."""
    # Trường hợp 1: Action không tồn tại
    monkeypatch.setattr(
        _hrr_mod,
        "interrupt",
        MagicMock(return_value={"analysis_revision": 1, "action": "reject"}),
    )
    state = _make_state(analysis_revision=1)
    with pytest.raises(ValidationError):
        human_review_recommendation(state)

    # Trường hợp 2: analysis_revision < 1
    monkeypatch.setattr(
        _hrr_mod,
        "interrupt",
        MagicMock(return_value={"analysis_revision": 0, "action": "submit"}),
    )
    with pytest.raises(ValidationError):
        human_review_recommendation(state)


# ==============================================================================
# Nhóm 2: Router buyer_decision_router (Decision Routing)
# ==============================================================================
def test_tc_hrr_10_router_submit_action() -> None:
    """TC-HRR-10: Router định tuyến SUBMIT -> 'submit'."""
    req = BuyerSubmitApprovalRequest(
        analysis_revision=1,
        action=BuyerAction.SUBMIT,
        note="Approved",
    )
    state: dict[str, Any] = {"buyer_approval_request": req}
    assert buyer_decision_router(state) == "submit"


def test_tc_hrr_11_router_revise_action() -> None:
    """TC-HRR-11: Router định tuyến REVISE -> 'revise'."""
    req = BuyerSubmitApprovalRequest(
        analysis_revision=1,
        action=BuyerAction.REVISE,
        note="Needs revision",
    )
    state: dict[str, Any] = {"buyer_approval_request": req}
    assert buyer_decision_router(state) == "revise"


def test_tc_hrr_12_router_missing_request_invalid() -> None:
    """TC-HRR-12: Router định tuyến INVALID khi thiếu request."""
    # State rỗng
    assert buyer_decision_router({}) == "invalid"
    # State có key nhưng giá trị None
    assert buyer_decision_router({"buyer_approval_request": None}) == "invalid"
