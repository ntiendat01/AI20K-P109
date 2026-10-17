from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.domain.agent.quotation.extraction import (
    ValidatedExtraction,
    ValidationSeverity,
)


def _load_validate_extraction():
    """Load validate_extraction node directly to enable fully isolated testing.

    This prevents test collection or execution from executing unrelated imports in
    src.agents.nodes.__init__.py during schema migration.
    """
    node_path = Path(__file__).resolve().parent.parent / "src" / "agents" / "nodes" / "validate_extraction.py"
    spec = importlib.util.spec_from_file_location("validate_extraction_node", node_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {node_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_extraction


validate_extraction = _load_validate_extraction()


# ==============================================================================
# TC-01 — Happy Path: Draft hợp lệ hoàn hảo, không có bất kỳ issue nào
# ==============================================================================
def test_tc01_happy_path_perfect_draft_has_no_issues() -> None:
    state: dict[str, Any] = {
        "raw_extractions": [
            {
                "supplier_name": {
                    "value": "Công ty ABC",
                    "confidence": "0.95",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"},
                },
                "currency": {
                    "value": "VND",
                    "confidence": "0.99",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b2"},
                },
                "vat_rate": {
                    "value": "0.10",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b3"},
                },
                "items": [
                    {
                        "source_item_id": "item-1",
                        "product_name": {
                            "value": "Laptop Dell",
                            "confidence": "0.92",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b4"},
                        },
                        "unit": {
                            "value": "cái",
                            "confidence": "0.90",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b5"},
                        },
                        "quantity": {
                            "value": "2",
                            "confidence": "0.95",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b6"},
                        },
                        "unit_price": {
                            "value": "20000000.00",
                            "confidence": "0.91",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b7"},
                        },
                    }
                ],
            }
        ]
    }

    result = validate_extraction(state)
    assert result["review_mode"] == "mandatory"
    assert len(result["validated_extractions"]) == 1

    val: ValidatedExtraction = result["validated_extractions"][0]
    assert val.schema_valid is True
    assert val.human_confirmation_required is True
    assert val.issues == []


# ==============================================================================
# TC-02 — Boundary Confidence: Kiểm tra chính xác tại ngưỡng 0.80
# ==============================================================================
def test_tc02_boundary_confidence_at_threshold() -> None:
    draft_a: dict[str, Any] = {
        "supplier_name": {
            "value": "NCC Biên Đạt",
            "confidence": "0.80",
            "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"},
        },
        "currency": {
            "value": "VND",
            "confidence": "0.90",
            "source": {"document_id": "d1", "page_number": 1, "block_id": "b2"},
        },
        "items": [
            {
                "source_item_id": "item-1",
                "product_name": {
                    "value": "Hàng A",
                    "confidence": "0.80",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b3"},
                },
                "unit": {
                    "value": "cái",
                    "confidence": "0.80",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b4"},
                },
                "quantity": {
                    "value": "1",
                    "confidence": "0.80",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b5"},
                },
                "unit_price": {
                    "value": "100000.00",
                    "confidence": "0.80",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b6"},
                },
            }
        ],
    }

    draft_b: dict[str, Any] = {
        "supplier_name": {
            "value": "NCC Cảnh Báo",
            "confidence": "0.79",
            "source": {"document_id": "d1", "page_number": 1, "block_id": "b7"},
        },
        "currency": {
            "value": "VND",
            "confidence": "0.90",
            "source": {"document_id": "d1", "page_number": 1, "block_id": "b8"},
        },
        "items": [
            {
                "source_item_id": "item-1",
                "product_name": {
                    "value": "Hàng B",
                    "confidence": "0.80",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b9"},
                },
                "unit": {
                    "value": "cái",
                    "confidence": "0.80",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b10"},
                },
                "quantity": {
                    "value": "1",
                    "confidence": "0.80",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b11"},
                },
                "unit_price": {
                    "value": "100000.00",
                    "confidence": "0.80",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b12"},
                },
            }
        ],
    }

    result = validate_extraction({"raw_extractions": [draft_a, draft_b]})
    assert len(result["validated_extractions"]) == 2

    # Với Draft A (0.80): Biên đạt chuẩn -> Không có LOW_CONFIDENCE
    val_a: ValidatedExtraction = result["validated_extractions"][0]
    assert val_a.schema_valid is True
    low_conf_issues_a = [i for i in val_a.issues if i.code == "LOW_CONFIDENCE"]
    assert low_conf_issues_a == []

    # Với Draft B (0.79): Dưới biên 0.01 -> Cảnh báo LOW_CONFIDENCE
    val_b: ValidatedExtraction = result["validated_extractions"][1]
    assert val_b.schema_valid is True
    assert len(val_b.issues) == 1
    issue = val_b.issues[0]
    assert issue.field_path == "supplier_name"
    assert issue.code == "LOW_CONFIDENCE"
    assert issue.severity == ValidationSeverity.WARNING
    assert issue.confidence == Decimal("0.79")


# ==============================================================================
# TC-03 — Missing Provenance: Có giá trị nhưng thiếu nguồn gốc (source = None)
# ==============================================================================
def test_tc03_missing_provenance_triggers_warning() -> None:
    state: dict[str, Any] = {
        "raw_extractions": [
            {
                "supplier_name": {
                    "value": "NCC X",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"},
                },
                "currency": {
                    "value": "VND",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b2"},
                },
                "items": [
                    {
                        "source_item_id": "item-1",
                        "product_name": {
                            "value": "Màn hình",
                            "confidence": "0.90",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b3"},
                        },
                        "unit": {
                            "value": "cái",
                            "confidence": "0.90",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b4"},
                        },
                        "quantity": {
                            "value": "1",
                            "confidence": "0.90",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b5"},
                        },
                        "unit_price": {
                            "value": "5000000.00",
                            "confidence": "0.95",
                            "source": None,
                        },
                    }
                ],
            }
        ]
    }

    result = validate_extraction(state)
    val: ValidatedExtraction = result["validated_extractions"][0]
    assert val.schema_valid is True
    assert len(val.issues) == 1

    issue = val.issues[0]
    assert issue.field_path == "items[0].unit_price"
    assert issue.code == "MISSING_PROVENANCE"
    assert issue.severity == ValidationSeverity.WARNING


# ==============================================================================
# TC-04 — Missing Required Fields: Thiếu trường bắt buộc ở Header & Item
# ==============================================================================
def test_tc04_missing_required_fields_header_and_item() -> None:
    state: dict[str, Any] = {
        "raw_extractions": [
            {
                "supplier_name": None,
                "currency": {
                    "value": "VND",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"},
                },
                "items": [
                    {
                        "source_item_id": "item-1",
                        "product_name": {
                            "value": "   ",
                            "confidence": "0.90",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b2"},
                        },
                        "unit": {
                            "value": "cái",
                            "confidence": "0.90",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b3"},
                        },
                        "quantity": {
                            "value": "1",
                            "confidence": "0.90",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b4"},
                        },
                        "unit_price": {
                            "value": "1000.00",
                            "confidence": "0.90",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b5"},
                        },
                    }
                ],
            }
        ]
    }

    result = validate_extraction(state)
    val: ValidatedExtraction = result["validated_extractions"][0]
    assert val.schema_valid is False

    blocking_paths = [i.field_path for i in val.issues if i.severity == ValidationSeverity.BLOCKING]
    assert "supplier_name" in blocking_paths
    assert "items[0].product_name" in blocking_paths

    for issue in val.issues:
        if issue.field_path in ("supplier_name", "items[0].product_name"):
            assert issue.code == "MISSING_REQUIRED_FIELD"
            assert issue.severity == ValidationSeverity.BLOCKING


# ==============================================================================
# TC-05 — Empty Items List: Danh sách items rỗng
# ==============================================================================
def test_tc05_empty_items_list_blocks_draft() -> None:
    state: dict[str, Any] = {
        "raw_extractions": [
            {
                "supplier_name": {
                    "value": "NCC A",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"},
                },
                "currency": {
                    "value": "VND",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b2"},
                },
                "items": [],
            }
        ]
    }

    result = validate_extraction(state)
    val: ValidatedExtraction = result["validated_extractions"][0]
    assert val.schema_valid is False

    item_issues = [i for i in val.issues if i.field_path == "items"]
    assert len(item_issues) == 1
    assert item_issues[0].code == "MISSING_ITEMS"
    assert item_issues[0].severity == ValidationSeverity.BLOCKING


# ==============================================================================
# TC-06 — Optional Fields: Trường tùy chọn bị thiếu không tạo issue
# ==============================================================================
def test_tc06_optional_fields_absence_and_low_confidence() -> None:
    state: dict[str, Any] = {
        "raw_extractions": [
            {
                "supplier_name": {
                    "value": "NCC B",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"},
                },
                "currency": {
                    "value": "VND",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b2"},
                },
                "warranty_months": None,
                "payment_terms": {
                    "value": "30 ngày",
                    "confidence": "0.65",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b3"},
                },
                "items": [
                    {
                        "source_item_id": "item-1",
                        "product_name": {
                            "value": "Chuột quang",
                            "confidence": "0.90",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b4"},
                        },
                        "product_code": None,
                        "unit": {
                            "value": "cái",
                            "confidence": "0.90",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b5"},
                        },
                        "quantity": {
                            "value": "5",
                            "confidence": "0.90",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b6"},
                        },
                        "unit_price": {
                            "value": "150000.00",
                            "confidence": "0.90",
                            "source": {"document_id": "d1", "page_number": 1, "block_id": "b7"},
                        },
                    }
                ],
            }
        ]
    }

    result = validate_extraction(state)
    val: ValidatedExtraction = result["validated_extractions"][0]
    assert val.schema_valid is True

    # Trường tùy chọn bị thiếu không sinh issue
    assert not any(i.field_path == "warranty_months" for i in val.issues)
    assert not any(i.field_path == "items[0].product_code" for i in val.issues)

    # Có giá trị nhưng confidence < 0.80 vẫn sinh LOW_CONFIDENCE warning
    pt_issue = next(i for i in val.issues if i.field_path == "payment_terms")
    assert pt_issue.code == "LOW_CONFIDENCE"
    assert pt_issue.severity == ValidationSeverity.WARNING
    assert pt_issue.confidence == Decimal("0.65")


# ==============================================================================
# TC-07 — Pydantic Schema Failure: Dict đầu vào vỡ cấu trúc không parse được
# ==============================================================================
def test_tc07_pydantic_schema_failure_handled_gracefully() -> None:
    state: dict[str, Any] = {"raw_extractions": [{"items": "đây không phải là list"}]}

    result = validate_extraction(state)
    val: ValidatedExtraction = result["validated_extractions"][0]
    assert val.schema_valid is False
    assert len(val.issues) >= 1
    assert any(i.code == "SCHEMA_INVALID" and i.severity == ValidationSeverity.BLOCKING for i in val.issues)


# ==============================================================================
# TC-08 — Multiple Drafts & Empty State: Xử lý nhiều draft độc lập và danh sách rỗng
# ==============================================================================
def test_tc08_multiple_drafts_and_empty_state(sample_raw_draft_dict: dict[str, Any]) -> None:
    # 1. State danh sách rỗng
    empty_result = validate_extraction({"raw_extractions": []})
    assert empty_result["validated_extractions"] == []
    assert empty_result["review_mode"] == "mandatory"

    # 2. Xử lý nhiều draft đồng thời (1 draft hợp lệ, 1 draft lỗi)
    invalid_draft: dict[str, Any] = {
        "supplier_name": None,
        "currency": {
            "value": "VND",
            "confidence": "0.90",
            "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"},
        },
        "items": [],
    }

    multi_result = validate_extraction({"raw_extractions": [sample_raw_draft_dict, invalid_draft]})
    assert len(multi_result["validated_extractions"]) == 2
    assert multi_result["validated_extractions"][0].schema_valid is True
    assert multi_result["validated_extractions"][1].schema_valid is False


# ==============================================================================
# TC-09 — PyMuPDF Text Layer: Confidence là None/null không bị cảnh báo LOW_CONFIDENCE
# ==============================================================================
def test_tc09_pymupdf_null_confidence_does_not_trigger_low_confidence() -> None:
    draft: dict[str, Any] = {
        "supplier_name": {
            "value": "Công ty Digital PDF",
            "confidence": None,
            "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"},
        },
        "currency": {
            "value": "VND",
            "confidence": None,
            "source": {"document_id": "d1", "page_number": 1, "block_id": "b2"},
        },
        "items": [
            {
                "source_item_id": "item-1",
                "product_name": {
                    "value": "Sản phẩm A",
                    "confidence": None,
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b3"},
                },
                "unit": {
                    "value": "cái",
                    "confidence": None,
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b4"},
                },
                "quantity": {
                    "value": "5",
                    "confidence": None,
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b5"},
                },
                "unit_price": {
                    "value": "500000.00",
                    "confidence": None,
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b6"},
                },
            }
        ],
    }
    result = validate_extraction({"raw_extractions": [draft]})
    val: ValidatedExtraction = result["validated_extractions"][0]
    assert val.schema_valid is True
    low_conf_issues = [i for i in val.issues if i.code == "LOW_CONFIDENCE"]
    assert low_conf_issues == []
