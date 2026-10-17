from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.domain.agent.quotation.confirmation import (
    ConfirmedItemPayload,
    QuotationConfirmationRequest,
)
from src.domain.agent.quotation.extraction import (
    ValidatedExtraction,
    ValidationIssue,
    ValidationSeverity,
)


def _load_human_review_extraction_module():
    """Load human_review_extraction node module directly to enable isolated execution."""
    node_path = Path(__file__).resolve().parent.parent / "src" / "agents" / "nodes" / "human_review_extraction.py"
    spec = importlib.util.spec_from_file_location("human_review_extraction_node", node_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {node_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_node_mod = _load_human_review_extraction_module()
human_review_extraction = _node_mod.human_review_extraction
ConfirmationCountError = _node_mod.ConfirmationCountError
UnknownSourceItemError = _node_mod.UnknownSourceItemError


def _make_raw_draft(
    supplier_name: str = "Công ty ABC",
    item_ids: list[str] | None = None,
) -> dict[str, Any]:
    if item_ids is None:
        item_ids = ["item-1"]
    return {
        "supplier_name": {
            "value": supplier_name,
            "confidence": "0.95",
            "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"},
        },
        "currency": {
            "value": "VND",
            "confidence": "0.99",
            "source": {"document_id": "d1", "page_number": 1, "block_id": "b2"},
        },
        "items": [
            {
                "source_item_id": item_id,
                "product_name": {
                    "value": f"Product {item_id}",
                    "confidence": "0.92",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": f"b-{item_id}"},
                },
                "unit": {
                    "value": "cái",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b-u"},
                },
                "quantity": {
                    "value": "2",
                    "confidence": "0.95",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b-q"},
                },
                "unit_price": {
                    "value": "20000000.00",
                    "confidence": "0.91",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b-p"},
                },
            }
            for item_id in item_ids
        ],
    }


def _make_buyer_confirmation_dict(
    supplier_name: str = "Công ty ABC",
    items: list[dict[str, Any]] | None = None,
    review_note: str | None = None,
) -> dict[str, Any]:
    if items is None:
        items = [
            {
                "source_item_id": "item-1",
                "product_name": "Laptop Dell Core i7",
                "product_code": "DELL-5520",
                "unit": "cái",
                "quantity": "2",
                "unit_price": "20000000.00",
            }
        ]
    return {
        "supplier_name": supplier_name,
        "currency": "VND",
        "vat_rate": "0.10",
        "vat_included": True,
        "lead_time_days": 7,
        "warranty_months": 12,
        "payment_terms": "30 ngày",
        "items": items,
        "review_note": review_note,
    }


# ==============================================================================
# TC-01 — Happy Path: Buyer xác nhận 1 draft đơn lẻ hợp lệ hoàn hảo
# ==============================================================================
def test_tc01_happy_path_single_draft_confirmed(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_draft = _make_raw_draft("Công ty ABC", ["item-1"])
    validation = ValidatedExtraction(schema_valid=True, issues=[])

    state: dict[str, Any] = {
        "raw_extractions": [raw_draft],
        "validated_extractions": [validation],
    }

    buyer_response = [_make_buyer_confirmation_dict("Công ty ABC", review_note="Đã thương lượng bảo hành")]

    mock_interrupt = MagicMock(return_value=buyer_response)
    monkeypatch.setattr(_node_mod, "interrupt", mock_interrupt)

    result = human_review_extraction(state)

    # 1. Kiểm tra interrupt payload
    mock_interrupt.assert_called_once()
    call_payload = mock_interrupt.call_args[0][0]
    assert call_payload["checkpoint"] == "extraction_review"
    assert call_payload["review_mode"] == "mandatory"
    assert len(call_payload["drafts"]) == 1
    assert call_payload["drafts"][0]["supplier_name"]["value"] == "Công ty ABC"
    assert len(call_payload["validations"]) == 1
    assert call_payload["validations"][0]["schema_valid"] is True

    # 2. Kiểm tra output state
    assert "confirmed_quotes" in result
    assert len(result["confirmed_quotes"]) == 1
    confirmed = result["confirmed_quotes"][0]
    assert isinstance(confirmed, QuotationConfirmationRequest)
    assert confirmed.supplier_name == "Công ty ABC"
    assert confirmed.currency == "VND"
    assert confirmed.vat_rate == Decimal("0.10")
    assert confirmed.vat_included is True
    assert confirmed.lead_time_days == 7
    assert confirmed.warranty_months == 12
    assert confirmed.payment_terms == "30 ngày"
    assert len(confirmed.items) == 1
    assert confirmed.items[0].source_item_id == "item-1"
    assert confirmed.items[0].quantity == Decimal("2")
    assert confirmed.items[0].unit_price == Decimal("20000000.00")
    assert confirmed.review_note == "Đã thương lượng bảo hành"


# ==============================================================================
# TC-02 — Buyer Manual Addition: Buyer thêm mới dòng hàng bằng tay (source_item_id = None)
# ==============================================================================
def test_tc02_buyer_manual_addition_with_none_source_item_id(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_draft = _make_raw_draft("Công ty ABC", ["item-1"])
    state: dict[str, Any] = {
        "raw_extractions": [raw_draft],
        "validated_extractions": [ValidatedExtraction(schema_valid=True, issues=[])],
    }

    buyer_response = [
        _make_buyer_confirmation_dict(
            "Công ty ABC",
            items=[
                {
                    "source_item_id": "item-1",
                    "product_name": "Server Dell R740",
                    "unit": "bộ",
                    "quantity": "1",
                    "unit_price": "80000000.00",
                },
                {
                    "source_item_id": None,  # Thêm thủ công
                    "product_name": "Gói cài đặt & bảo trì 1 năm",
                    "unit": "gói",
                    "quantity": "1",
                    "unit_price": "5000000.00",
                },
            ],
        )
    ]

    monkeypatch.setattr(_node_mod, "interrupt", MagicMock(return_value=buyer_response))

    result = human_review_extraction(state)
    assert len(result["confirmed_quotes"]) == 1
    items: list[ConfirmedItemPayload] = result["confirmed_quotes"][0].items
    assert len(items) == 2
    assert items[0].source_item_id == "item-1"
    assert items[1].source_item_id is None
    assert items[1].product_name == "Gói cài đặt & bảo trì 1 năm"


# ==============================================================================
# TC-03 — Payload Contract: Kiểm tra tính toàn vẹn của dữ liệu gửi vào interrupt
# ==============================================================================
def test_tc03_payload_contract_sent_to_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_draft = _make_raw_draft("NCC Test", ["item-10"])
    warning_issue = ValidationIssue(
        field_path="items[0].unit_price",
        code="LOW_CONFIDENCE",
        severity=ValidationSeverity.WARNING,
        confidence=Decimal("0.75"),
    )
    validation = ValidatedExtraction(schema_valid=True, issues=[warning_issue])

    state: dict[str, Any] = {
        "raw_extractions": [raw_draft],
        "validated_extractions": [validation],
    }

    mock_interrupt = MagicMock(
        return_value=[
            _make_buyer_confirmation_dict(
                "NCC Test",
                items=[
                    {
                        "source_item_id": "item-10",
                        "product_name": "Product 10",
                        "unit": "cái",
                        "quantity": "1",
                        "unit_price": "1000.00",
                    }
                ],
            )
        ]
    )
    monkeypatch.setattr(_node_mod, "interrupt", mock_interrupt)

    human_review_extraction(state)

    call_args = mock_interrupt.call_args[0][0]
    assert call_args["checkpoint"] == "extraction_review"
    assert call_args["review_mode"] == "mandatory"
    assert len(call_args["drafts"]) == 1
    assert call_args["drafts"][0]["supplier_name"]["value"] == "NCC Test"
    assert len(call_args["validations"]) == 1
    assert call_args["validations"][0]["schema_valid"] is True
    assert len(call_args["validations"][0]["issues"]) == 1
    assert call_args["validations"][0]["issues"][0]["code"] == "LOW_CONFIDENCE"
    assert call_args["validations"][0]["issues"][0]["field_path"] == "items[0].unit_price"


# ==============================================================================
# TC-04 — Confirmation Count Mismatch: Lệch số lượng confirmation vs drafts
# ==============================================================================
def test_tc04_confirmation_count_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    draft_1 = _make_raw_draft("NCC 1", ["item-1"])
    draft_2 = _make_raw_draft("NCC 2", ["item-2"])

    # 1. State có 2 draft nhưng Buyer gửi 1 confirmation -> expected=2, actual=1
    state_2_drafts: dict[str, Any] = {
        "raw_extractions": [draft_1, draft_2],
        "validated_extractions": [],
    }
    monkeypatch.setattr(
        _node_mod,
        "interrupt",
        MagicMock(
            return_value=[
                _make_buyer_confirmation_dict(
                    "NCC 1",
                    items=[
                        {
                            "source_item_id": "item-1",
                            "product_name": "A",
                            "unit": "cái",
                            "quantity": "1",
                            "unit_price": "10.00",
                        }
                    ],
                )
            ]
        ),
    )

    with pytest.raises(ConfirmationCountError) as exc_info_1:
        human_review_extraction(state_2_drafts)
    assert exc_info_1.value.expected == 2
    assert exc_info_1.value.actual == 1
    assert "Expected 2 quotation confirmations, received 1" in str(exc_info_1.value)

    # 2. State có 1 draft nhưng Buyer gửi 2 confirmations -> expected=1, actual=2
    state_1_draft: dict[str, Any] = {
        "raw_extractions": [draft_1],
        "validated_extractions": [],
    }
    conf_1 = _make_buyer_confirmation_dict(
        "NCC 1",
        items=[
            {
                "source_item_id": "item-1",
                "product_name": "A",
                "unit": "cái",
                "quantity": "1",
                "unit_price": "10.00",
            }
        ],
    )
    conf_2 = _make_buyer_confirmation_dict(
        "NCC 2",
        items=[
            {
                "source_item_id": "item-2",
                "product_name": "B",
                "unit": "cái",
                "quantity": "1",
                "unit_price": "20.00",
            }
        ],
    )
    monkeypatch.setattr(_node_mod, "interrupt", MagicMock(return_value=[conf_1, conf_2]))

    with pytest.raises(ConfirmationCountError) as exc_info_2:
        human_review_extraction(state_1_draft)
    assert exc_info_2.value.expected == 1
    assert exc_info_2.value.actual == 2
    assert "Expected 1 quotation confirmations, received 2" in str(exc_info_2.value)


# ==============================================================================
# TC-05 — Lineage Violation: Dòng hàng mang source_item_id lạ không thuộc draft
# ==============================================================================
def test_tc05_lineage_violation_unknown_source_item_id(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_draft = _make_raw_draft("NCC A", ["item-A"])
    state: dict[str, Any] = {
        "raw_extractions": [raw_draft],
        "validated_extractions": [],
    }

    buyer_response = [
        _make_buyer_confirmation_dict(
            "NCC A",
            items=[
                {
                    "source_item_id": "item-UNKNOWN-999",  # Không thuộc draft
                    "product_name": "Thiết bị lạ",
                    "unit": "cái",
                    "quantity": "1",
                    "unit_price": "500000.00",
                }
            ],
        )
    ]

    monkeypatch.setattr(_node_mod, "interrupt", MagicMock(return_value=buyer_response))

    with pytest.raises(UnknownSourceItemError) as exc_info:
        human_review_extraction(state)
    assert exc_info.value.source_item_id == "item-UNKNOWN-999"
    assert "Confirmed source item does not belong to its extraction draft: item-UNKNOWN-999" in str(exc_info.value)


# ==============================================================================
# TC-06 — Invalid Confirmation Schema: Response không thỏa mãn schema Pydantic
# ==============================================================================
def test_tc06_invalid_confirmation_schema_triggers_pydantic_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_draft = _make_raw_draft("NCC A", ["item-1"])
    state: dict[str, Any] = {
        "raw_extractions": [raw_draft],
        "validated_extractions": [],
    }

    # Thiếu vat_rate và items=[] (vi phạm min_length=1)
    invalid_buyer_response = [
        {
            "supplier_name": "Công ty ABC",
            "currency": "VND",
            # vat_rate bị thiếu
            "vat_included": True,
            "lead_time_days": 7,
            "warranty_months": 12,
            "payment_terms": "30 ngày",
            "items": [],
        }
    ]

    monkeypatch.setattr(_node_mod, "interrupt", MagicMock(return_value=invalid_buyer_response))

    with pytest.raises(ValidationError) as exc_info:
        human_review_extraction(state)

    errors = exc_info.value.errors()
    field_paths = [".".join(str(p) for p in err["loc"]) for err in errors]
    assert any("vat_rate" in p for p in field_paths)
    assert any("items" in p for p in field_paths)


# ==============================================================================
# TC-07 — Multiple Drafts Correspondence: Xử lý nhiều báo giá đồng thời đúng thứ tự
# ==============================================================================
def test_tc07_multiple_drafts_correspondence_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    draft_1 = _make_raw_draft("NCC 1", ["item-A1"])
    draft_2 = _make_raw_draft("NCC 2", ["item-B1"])

    state: dict[str, Any] = {
        "raw_extractions": [draft_1, draft_2],
        "validated_extractions": [],
    }

    conf_1 = _make_buyer_confirmation_dict(
        "NCC 1",
        items=[
            {
                "source_item_id": "item-A1",
                "product_name": "SP NCC 1",
                "unit": "cái",
                "quantity": "5",
                "unit_price": "10000.00",
            }
        ],
    )
    conf_2 = _make_buyer_confirmation_dict(
        "NCC 2",
        items=[
            {
                "source_item_id": "item-B1",
                "product_name": "SP NCC 2",
                "unit": "cái",
                "quantity": "10",
                "unit_price": "9000.00",
            }
        ],
    )

    monkeypatch.setattr(_node_mod, "interrupt", MagicMock(return_value=[conf_1, conf_2]))

    result = human_review_extraction(state)
    assert len(result["confirmed_quotes"]) == 2
    assert result["confirmed_quotes"][0].supplier_name == "NCC 1"
    assert result["confirmed_quotes"][0].items[0].source_item_id == "item-A1"
    assert result["confirmed_quotes"][1].supplier_name == "NCC 2"
    assert result["confirmed_quotes"][1].items[0].source_item_id == "item-B1"

    # Tráo đổi thứ tự: conf_2 đặt trước conf_1 -> item-B1 bị kiểm tra đối chiếu với draft_1 -> Phải raise UnknownSourceItemError
    monkeypatch.setattr(_node_mod, "interrupt", MagicMock(return_value=[conf_2, conf_1]))
    with pytest.raises(UnknownSourceItemError) as exc_info:
        human_review_extraction(state)
    assert exc_info.value.source_item_id == "item-B1"


# ==============================================================================
# TC-08 — Empty State Handling: Danh sách drafts rỗng
# ==============================================================================
def test_tc08_empty_state_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, Any] = {
        "raw_extractions": [],
        "validated_extractions": [],
    }

    mock_interrupt = MagicMock(return_value=[])
    monkeypatch.setattr(_node_mod, "interrupt", mock_interrupt)

    result = human_review_extraction(state)
    assert result["confirmed_quotes"] == []
    mock_interrupt.assert_called_once_with(
        {
            "checkpoint": "extraction_review",
            "review_mode": "mandatory",
            "drafts": [],
            "validations": [],
        }
    )
