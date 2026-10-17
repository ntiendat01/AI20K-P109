from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.domain.agent.analysis.comparison import (
    SupplierComparisonMatrix,
)
from src.domain.agent.analysis.decision import (
    DecisionProposal,
    DecisionProposalStatus,
)
from src.domain.agent.analysis.normalization import (
    NormalizationStatus,
    NormalizedItem,
    NormalizedQuotationArtifact,
)
from src.domain.agent.analysis.risk import (
    RiskSeverity,
)
from src.domain.agent.analysis.tco import (
    TCOCalculationStatus,
    TCOResult,
)
from src.domain.agent.approval import (
    BuyerAction,
    BuyerSubmitApprovalRequest,
)
from src.domain.agent.quotation.confirmation import (
    ConfirmedItemPayload,
    QuotationConfirmationRequest,
)
from src.domain.agent.quotation.extraction import (
    ExtractionDraftPayload,
    ValidatedExtraction,
    ValidationSeverity,
)


# ==============================================================================
# Isolated Node Loaders (Không kích hoạt eager import của src.agents.nodes.__init__)
# ==============================================================================
def _load_node_module(filename: str):
    node_path = Path(__file__).resolve().parent.parent / "src" / "agents" / "nodes" / filename
    module_name = f"src.agents.nodes.{filename.replace('.py', '')}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, node_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {node_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_ext_mod = _load_node_module("extract_documents.py")
_val_mod = _load_node_module("validate_extraction.py")
_hitl_mod = _load_node_module("human_review_extraction.py")
_norm_mod = _load_node_module("normalize.py")
_analysis_mod = _load_node_module("analysis_tools.py")
_decision_mod = _load_node_module("decision_llm.py")
_hrr_mod = _load_node_module("human_review_recommendation.py")

extract_documents = _ext_mod.extract_documents
validate_extraction = _val_mod.validate_extraction
human_review_extraction = _hitl_mod.human_review_extraction
ConfirmationCountError = _hitl_mod.ConfirmationCountError
UnknownSourceItemError = _hitl_mod.UnknownSourceItemError
normalize = _norm_mod.normalize
calculate_tco_node = _analysis_mod.calculate_tco_node
compare_suppliers_node = _analysis_mod.compare_suppliers_node
analyze_risks_node = _analysis_mod.analyze_risks_node
decision_llm = _decision_mod.decision_llm
human_review_recommendation = _hrr_mod.human_review_recommendation
buyer_decision_router = _hrr_mod.buyer_decision_router
AnalysisRevisionMismatchError = _hrr_mod.AnalysisRevisionMismatchError


# ==============================================================================
# Stubs cho I/O bên ngoài (OCR / LLM extraction)
# ==============================================================================
class StubOCRClient:
    def __init__(self, text: str = "OCR sample text") -> None:
        self.text = text

    def extract_text(self, document_path: str) -> str:
        del document_path
        return self.text


class StubExtractionClient:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items

    def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, Any]]:
        del ocr_text, document_path
        return self.items


# ==============================================================================
# PHẦN 1: TEST BIÊN ĐƠN LẺ TỪNG NODE (Single-Node Boundary Contracts)
# ==============================================================================


# --- 1. extract_documents boundary ---
def test_tc_b01_extract_documents_boundary_valid_file(tmp_path: Path) -> None:
    doc = tmp_path / "quote.pdf"
    doc.write_bytes(b"%PDF-1.7 fixture")

    raw_item: dict[str, Any] = {
        "supplier_name": "Supplier A",
        "currency": "vnd",
        "product_name": "Laptop",
        "unit": "cái",
        "quantity": "5",
        "unit_price": "20000000.00",
        "page_number": 1,
        "confidence_score": 0.95,
    }

    state: dict[str, Any] = {"documents": [str(doc)]}
    result = extract_documents(
        state,
        ocr_client=StubOCRClient("text"),
        extraction_client=StubExtractionClient([raw_item]),
    )

    assert "raw_extractions" in result
    assert len(result["raw_extractions"]) == 1
    draft = result["raw_extractions"][0]
    assert draft["supplier_name"]["value"] == "Supplier A"
    assert draft["currency"]["value"] == "VND"
    assert len(draft["items"]) == 1
    assert draft["items"][0]["product_name"]["value"] == "Laptop"


def test_tc_b02_extract_documents_boundary_empty_file(tmp_path: Path) -> None:
    doc = tmp_path / "empty.pdf"
    doc.write_bytes(b"%PDF-1.7 empty")

    state: dict[str, Any] = {"documents": [str(doc)]}
    result = extract_documents(
        state,
        ocr_client=StubOCRClient("   "),
        extraction_client=StubExtractionClient([]),
    )

    assert len(result["raw_extractions"]) == 1
    draft = result["raw_extractions"][0]
    assert draft == ExtractionDraftPayload().model_dump(mode="json")
    assert draft["supplier_name"] is None
    assert draft["items"] == []


def test_tc_b03_extract_documents_boundary_empty_documents_list() -> None:
    result = extract_documents({"documents": []})
    assert result == {"raw_extractions": []}


# --- 2. validate_extraction boundary ---
def test_tc_b04_validate_extraction_boundary_valid_draft() -> None:
    valid_draft: dict[str, Any] = {
        "supplier_name": {
            "value": "ABC Corp",
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
                "source_item_id": "item-1",
                "product_name": {
                    "value": "Server",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b3"},
                },
                "unit": {
                    "value": "bộ",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b4"},
                },
                "quantity": {
                    "value": "1",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b5"},
                },
                "unit_price": {
                    "value": "50000000.00",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b6"},
                },
            }
        ],
    }

    result = validate_extraction({"raw_extractions": [valid_draft]})

    assert result["review_mode"] == "mandatory"
    assert len(result["validated_extractions"]) == 1
    val: ValidatedExtraction = result["validated_extractions"][0]
    assert val.schema_valid is True
    assert val.issues == []


def test_tc_b05_validate_extraction_boundary_missing_required_field() -> None:
    invalid_draft: dict[str, Any] = {
        "supplier_name": None,
        "currency": {
            "value": "VND",
            "confidence": "0.90",
            "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"},
        },
        "items": [],
    }

    result = validate_extraction({"raw_extractions": [invalid_draft]})
    val: ValidatedExtraction = result["validated_extractions"][0]

    assert val.schema_valid is False
    blocking_codes = [i.code for i in val.issues if i.severity == ValidationSeverity.BLOCKING]
    assert "MISSING_REQUIRED_FIELD" in blocking_codes
    assert "MISSING_ITEMS" in blocking_codes


def test_tc_b06_validate_extraction_boundary_low_confidence_warning() -> None:
    draft_with_warning: dict[str, Any] = {
        "supplier_name": {
            "value": "ABC Corp",
            "confidence": "0.75",
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
                    "value": "Server",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b3"},
                },
                "unit": {
                    "value": "bộ",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b4"},
                },
                "quantity": {
                    "value": "1",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b5"},
                },
                "unit_price": {
                    "value": "50000000.00",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b6"},
                },
            }
        ],
    }

    result = validate_extraction({"raw_extractions": [draft_with_warning]})
    val: ValidatedExtraction = result["validated_extractions"][0]

    assert val.schema_valid is True
    assert any(i.code == "LOW_CONFIDENCE" and i.severity == ValidationSeverity.WARNING for i in val.issues)


# --- 3. human_review_extraction boundary ---
def test_tc_b07_human_review_boundary_valid_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    draft: dict[str, Any] = {
        "supplier_name": {
            "value": "ABC Corp",
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
                    "value": "Server",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b3"},
                },
                "unit_price": {
                    "value": "50000000.00",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b4"},
                },
            }
        ],
    }
    buyer_response = [
        {
            "supplier_name": "ABC Corp",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 7,
            "warranty_months": 24,
            "payment_terms": "30 ngày",
            "items": [
                {
                    "source_item_id": "item-1",
                    "product_name": "Server",
                    "unit": "bộ",
                    "quantity": "1",
                    "unit_price": "50000000.00",
                }
            ],
        }
    ]

    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=buyer_response))

    result = human_review_extraction({"raw_extractions": [draft], "validated_extractions": []})
    assert len(result["confirmed_quotes"]) == 1
    confirmed = result["confirmed_quotes"][0]
    assert isinstance(confirmed, QuotationConfirmationRequest)
    assert confirmed.supplier_name == "ABC Corp"
    assert confirmed.items[0].unit_price == Decimal("50000000.00")


def test_tc_b08_human_review_boundary_count_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    draft_1: dict[str, Any] = {"items": []}
    draft_2: dict[str, Any] = {"items": []}
    state = {"raw_extractions": [draft_1, draft_2]}

    monkeypatch.setattr(
        _hitl_mod,
        "interrupt",
        MagicMock(
            return_value=[
                {
                    "supplier_name": "A",
                    "currency": "VND",
                    "vat_rate": "0.10",
                    "vat_included": True,
                    "lead_time_days": 1,
                    "warranty_months": 1,
                    "payment_terms": "net 30",
                    "items": [{"product_name": "P", "unit": "u", "quantity": "1", "unit_price": "100.00"}],
                }
            ]
        ),
    )

    with pytest.raises(ConfirmationCountError) as exc_info:
        human_review_extraction(state)
    assert exc_info.value.expected == 2
    assert exc_info.value.actual == 1


def test_tc_b09_human_review_boundary_unknown_source_item(monkeypatch: pytest.MonkeyPatch) -> None:
    draft: dict[str, Any] = {
        "items": [
            {
                "source_item_id": "item-VALID",
                "product_name": {
                    "value": "P",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b1"},
                },
                "unit_price": {
                    "value": "10.00",
                    "confidence": "0.90",
                    "source": {"document_id": "d1", "page_number": 1, "block_id": "b2"},
                },
            }
        ]
    }
    buyer_response = [
        {
            "supplier_name": "A",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 1,
            "warranty_months": 1,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": "item-UNKNOWN-X",
                    "product_name": "P",
                    "unit": "u",
                    "quantity": "1",
                    "unit_price": "100.00",
                }
            ],
        }
    ]

    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=buyer_response))

    with pytest.raises(UnknownSourceItemError) as exc_info:
        human_review_extraction({"raw_extractions": [draft]})
    assert exc_info.value.source_item_id == "item-UNKNOWN-X"


# --- 4. normalize boundary ---
def test_tc_b10_normalize_boundary_success() -> None:
    confirmed_quote = QuotationConfirmationRequest(
        supplier_name="NCC Global",
        currency="USD",
        vat_rate=Decimal("0.10"),
        vat_included=True,
        lead_time_days=7,
        warranty_months=12,
        payment_terms="30 days",
        items=[
            ConfirmedItemPayload(
                product_name="Bút bi",
                unit="hộp",
                quantity=Decimal("2"),
                unit_price=Decimal("200.00"),
            )
        ],
    )

    state: dict[str, Any] = {
        "confirmed_quotes": [confirmed_quote],
        "pr_data": {"target_uom": "cái", "target_currency": "VND"},
    }

    result = normalize(state)
    assert len(result["normalized_quotes"]) == 1

    artifact: NormalizedQuotationArtifact = result["normalized_quotes"][0]
    assert artifact.status == NormalizationStatus.NORMALIZED
    assert artifact.issues == []
    assert len(artifact.items) == 1

    item: NormalizedItem = artifact.items[0]
    # 1 hộp = 10 cái -> 2 hộp = 20 cái
    assert item.normalized_quantity == Decimal("20")
    assert item.normalized_uom == "cái"
    # 200.00 USD / 10 * 25400 = 508,000.00 VND
    assert item.normalized_unit_price == Decimal("508000.00")
    assert item.normalized_currency == "VND"
    assert item.rule_id == "uom:hộp->cái;fx:USD->VND"


def test_tc_b11_normalize_boundary_incompatible_uom() -> None:
    confirmed_quote = QuotationConfirmationRequest(
        supplier_name="NCC Thép",
        currency="VND",
        vat_rate=Decimal("0.10"),
        vat_included=True,
        lead_time_days=5,
        warranty_months=12,
        payment_terms="Giao ngay",
        items=[
            ConfirmedItemPayload(
                product_name="Thép tấm",
                unit="kg",
                quantity=Decimal("10"),
                unit_price=Decimal("50000.00"),
            )
        ],
    )

    state: dict[str, Any] = {
        "confirmed_quotes": [confirmed_quote],
        "pr_data": {"target_uom": "cái", "target_currency": "VND"},
    }

    result = normalize(state)
    artifact: NormalizedQuotationArtifact = result["normalized_quotes"][0]

    assert artifact.status == NormalizationStatus.NEEDS_MAPPING
    assert any("missing UOM mapping 'kg' -> 'cái'" in issue for issue in artifact.issues)
    assert artifact.items[0].normalized_quantity is None
    assert artifact.items[0].normalized_unit_price is None
    assert artifact.items[0].source_quantity == Decimal("10")
    assert artifact.items[0].source_uom == "kg"


def test_tc_b12_normalize_boundary_empty_confirmed_quotes() -> None:
    result = normalize({"confirmed_quotes": []})
    assert result == {"normalized_quotes": []}


# ==============================================================================
# PHẦN 2: TEST BIÊN TOÀN LUỒNG (End-to-End Chain Boundary: 4 Nodes Nối Tiếp)
# ==============================================================================


def test_tc_flow01_happy_path_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """PDF -> extract_documents -> validate_extraction -> human_review_extraction -> normalize."""
    doc_path = tmp_path / "quote_supplier_abc.pdf"
    doc_path.write_bytes(b"%PDF-1.7 fixture content")

    raw_ocr_item: dict[str, Any] = {
        "supplier_name": "Công ty ABC",
        "currency": "usd",
        "product_name": "Laptop Dell Precision",
        "product_code": "DELL-7550",
        "unit": "thùng",
        "quantity": "1",
        "unit_price": "20000.00",
        "page_number": 1,
        "confidence_score": 0.95,
    }

    # Node 1: extract_documents
    state_0: dict[str, Any] = {
        "documents": [str(doc_path)],
        "pr_data": {"target_uom": "cái", "target_currency": "VND"},
    }
    state_1 = {
        **state_0,
        **extract_documents(
            state_0,
            ocr_client=StubOCRClient("sample ocr"),
            extraction_client=StubExtractionClient([raw_ocr_item]),
        ),
    }

    # Node 2: validate_extraction
    state_2 = {
        **state_1,
        **validate_extraction(state_1),
    }

    # Node 3: human_review_extraction (Buyer duyệt)
    generated_item_id = state_1["raw_extractions"][0]["items"][0]["source_item_id"]
    buyer_response = [
        {
            "supplier_name": "Công ty ABC",
            "currency": "USD",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 10,
            "warranty_months": 36,
            "payment_terms": "Chuyển khoản 100% khi nhận hàng",
            "items": [
                {
                    "source_item_id": generated_item_id,
                    "product_name": "Laptop Dell Precision",
                    "product_code": "DELL-7550",
                    "unit": "thùng",
                    "quantity": "1",
                    "unit_price": "20000.00",
                }
            ],
            "review_note": "Báo giá chuẩn thùng 200 cái, giá 20k USD",
        }
    ]
    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=buyer_response))

    state_3 = {
        **state_2,
        **human_review_extraction(state_2),
    }

    # Node 4: normalize
    state_final = {
        **state_3,
        **normalize(state_3),
    }

    # CHỈ ASSERT TẠI BIÊN ĐẦU RA CUỐI CÙNG:
    assert "normalized_quotes" in state_final
    assert len(state_final["normalized_quotes"]) == 1

    norm_artifact: NormalizedQuotationArtifact = state_final["normalized_quotes"][0]
    assert norm_artifact.status == NormalizationStatus.NORMALIZED
    assert norm_artifact.issues == []
    assert len(norm_artifact.items) == 1

    # 1 thùng = 200 cái
    assert norm_artifact.items[0].normalized_quantity == Decimal("200")
    assert norm_artifact.items[0].normalized_uom == "cái"
    # 20,000 USD / 200 * 25,400 = 100 * 25,400 = 2,540,000.00 VND
    assert norm_artifact.items[0].normalized_unit_price == Decimal("2540000.00")
    assert norm_artifact.items[0].normalized_currency == "VND"


def test_tc_flow02_low_confidence_warning_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """PDF mờ (confidence thấp) -> Extract -> Validate cảnh báo -> Buyer sửa giá -> Normalize."""
    doc_path = tmp_path / "quote_blurry.pdf"
    doc_path.write_bytes(b"%PDF-1.7 blurry content")

    raw_ocr_item: dict[str, Any] = {
        "supplier_name": "Công ty XYZ",
        "currency": "vnd",
        "product_name": "Màn hình 4K",
        "unit": "cái",
        "quantity": "1",
        "unit_price": "12000000.00",
        "page_number": 1,
        "confidence_score": 0.65,
        "field_confidence": {"unit_price": 0.65},
    }

    state_0: dict[str, Any] = {
        "documents": [str(doc_path)],
        "pr_data": {"target_uom": "cái", "target_currency": "VND"},
    }
    state_1 = {
        **state_0,
        **extract_documents(
            state_0,
            ocr_client=StubOCRClient("ocr text"),
            extraction_client=StubExtractionClient([raw_ocr_item]),
        ),
    }
    state_2 = {
        **state_1,
        **validate_extraction(state_1),
    }

    # Biên giữa: Node 2 phát hiện cảnh báo LOW_CONFIDENCE
    val: ValidatedExtraction = state_2["validated_extractions"][0]
    assert any(i.code == "LOW_CONFIDENCE" for i in val.issues)

    # Buyer đối soát và chỉnh sửa lại giá chuẩn
    generated_item_id = state_1["raw_extractions"][0]["items"][0]["source_item_id"]
    buyer_response = [
        {
            "supplier_name": "Công ty XYZ",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": False,
            "lead_time_days": 3,
            "warranty_months": 12,
            "payment_terms": "Giao ngay",
            "items": [
                {
                    "source_item_id": generated_item_id,
                    "product_name": "Màn hình 4K",
                    "unit": "cái",
                    "quantity": "1",
                    "unit_price": "12500000.00",
                }
            ],
            "review_note": "Chỉnh sửa lại đơn giá mờ theo file scan gốc",
        }
    ]
    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=buyer_response))

    state_3 = {
        **state_2,
        **human_review_extraction(state_2),
    }
    state_final = {
        **state_3,
        **normalize(state_3),
    }

    # Biên đầu ra cuối cùng: Phản ánh đúng đơn giá Buyer đã hiệu chỉnh
    assert state_final["normalized_quotes"][0].status == NormalizationStatus.NORMALIZED
    assert state_final["normalized_quotes"][0].items[0].normalized_unit_price == Decimal("12500000.00")


def test_tc_flow03_lineage_tampering_rejected_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Toàn bộ luồng phát hiện và từ chối hành vi tráo đổi dòng hàng lạ trước khi đến normalize."""
    doc_path = tmp_path / "quote_audit.pdf"
    doc_path.write_bytes(b"%PDF-1.7 audit content")

    raw_ocr_item: dict[str, Any] = {
        "supplier_name": "NCC Hợp lệ",
        "currency": "vnd",
        "product_name": "Máy photocopy",
        "unit": "cái",
        "quantity": "1",
        "unit_price": "30000000.00",
        "page_number": 1,
        "confidence_score": 0.95,
    }

    state_1 = extract_documents(
        {"documents": [str(doc_path)]},
        ocr_client=StubOCRClient("ocr"),
        extraction_client=StubExtractionClient([raw_ocr_item]),
    )
    state_2 = {**state_1, **validate_extraction(state_1)}

    tampered_buyer_response = [
        {
            "supplier_name": "NCC Hợp lệ",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 5,
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": "item-TAMPERED-ID",
                    "product_name": "Máy photocopy",
                    "unit": "cái",
                    "quantity": "1",
                    "unit_price": "30000000.00",
                }
            ],
        }
    ]
    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=tampered_buyer_response))

    # Chặn đứng tại HITL-1, không lọt vào node normalize
    with pytest.raises(UnknownSourceItemError) as exc_info:
        human_review_extraction(state_2)
    assert exc_info.value.source_item_id == "item-TAMPERED-ID"


def test_tc_flow04_missing_required_field_rejected_at_hitl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Toàn luồng: Báo giá thiếu đơn giá, validate gắn cờ BLOCKING,

    Buyer confirm thiếu trường bắt buộc -> bị chặn đứng tại HITL-1.
    """
    doc_path = tmp_path / "quote_missing_price.pdf"
    doc_path.write_bytes(b"%PDF-1.7 missing price")

    raw_ocr_item: dict[str, Any] = {
        "supplier_name": "Công ty ABC",
        "currency": "vnd",
        "product_name": "Bàn phím cơ",
        "unit": "cái",
        "quantity": "5",
        "unit_price": "",  # Thiếu trường bắt buộc
        "page_number": 1,
        "confidence_score": 0.90,
    }

    # BƯỚC 1: extract_documents
    state_1 = extract_documents(
        {"documents": [str(doc_path)]},
        ocr_client=StubOCRClient("ocr text"),
        extraction_client=StubExtractionClient([raw_ocr_item]),
    )

    # BƯỚC 2: validate_extraction
    state_2 = {**state_1, **validate_extraction(state_1)}

    # Khẳng định ở biên Validate: Phải phát hiện lỗi BLOCKING
    validation = state_2["validated_extractions"][0]
    assert validation.schema_valid is False
    assert any(
        issue.severity == ValidationSeverity.BLOCKING
        and issue.code == "MISSING_REQUIRED_FIELD"
        and issue.field_path == "items[0].unit_price"
        for issue in validation.issues
    )

    # BƯỚC 3: Giả lập Buyer gửi response nhưng bỏ quên unit_price trong item
    source_item_id = state_1["raw_extractions"][0]["items"][0]["source_item_id"]
    invalid_buyer_response = [
        {
            "supplier_name": "Công ty ABC",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 3,
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": source_item_id,
                    "product_name": "Bàn phím cơ",
                    "unit": "cái",
                    "quantity": "5",
                    # THIẾU unit_price bắt buộc
                }
            ],
        }
    ]
    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=invalid_buyer_response))

    # BƯỚC 4: Khẳng định ở biên HITL-1
    # Schema validation phải từ chối ngay lập tức, không sinh ra confirmed_quotes
    with pytest.raises(ValidationError) as exc_info:
        human_review_extraction(state_2)

    errors = exc_info.value.errors()
    assert any("unit_price" in str(err["loc"]) and err["type"] == "missing" for err in errors)


def test_tc_flow05_analysis_subchain_normalize_tco_compare() -> None:
    """Chuỗi phân tích tất định: normalize -> calculate_tco -> compare_suppliers."""
    confirmed_quote_a = QuotationConfirmationRequest(
        supplier_name="NCC Toàn Cầu (Mỹ)",
        currency="USD",
        vat_rate=Decimal("0.10"),
        vat_included=True,
        lead_time_days=10,
        warranty_months=12,
        payment_terms="Net 30",
        items=[
            ConfirmedItemPayload(
                product_name="Màn hình Dell",
                unit="thùng",
                quantity=Decimal("1"),
                unit_price=Decimal("2000.00"),
            )
        ],
    )
    confirmed_quote_b = QuotationConfirmationRequest(
        supplier_name="NCC Hà Nội",
        currency="VND",
        vat_rate=Decimal("0.10"),
        vat_included=False,
        lead_time_days=15,
        warranty_months=24,
        payment_terms="Net 15",
        items=[
            ConfirmedItemPayload(
                product_name="Màn hình Dell",
                unit="cái",
                quantity=Decimal("200"),
                unit_price=Decimal("260000.00"),
            )
        ],
    )

    state_initial = {
        "confirmed_quotes": [confirmed_quote_a, confirmed_quote_b],
        "pr_data": {
            "target_uom": "cái",
            "target_currency": "VND",
        },
    }

    # BƯỚC 1: normalize
    state_norm = {**state_initial, **normalize(state_initial)}
    assert len(state_norm["normalized_quotes"]) == 2
    assert state_norm["normalized_quotes"][0].status == NormalizationStatus.NORMALIZED
    assert state_norm["normalized_quotes"][1].status == NormalizationStatus.NORMALIZED

    # BƯỚC 2: calculate_tco và analyze_risks (chạy song song sau normalize)
    due_date = (date.today() + timedelta(days=30)).isoformat()
    state_norm["pr_data"]["delivery_due_date"] = due_date
    state_tco = {
        **state_norm,
        **calculate_tco_node(state_norm),
        **analyze_risks_node(state_norm),
    }
    assert len(state_tco["tco_results"]) == 2
    assert state_tco["risk_flags"] == []  # Cả 2 NCC giao hàng trong 10-15 ngày, hạn 30 ngày -> không có rủi ro
    tco_a, tco_b = state_tco["tco_results"]
    assert tco_a.status == TCOCalculationStatus.CALCULATED
    assert tco_b.status == TCOCalculationStatus.CALCULATED
    # NCC A: 1 thùng = 200 cái, 2000 / 200 * 25400 = 254000.00 VND/cái -> 50.800.000 VND (VAT included)
    assert tco_a.total_tco == Decimal("50800000.00")
    # NCC B: 200 cái * 260.000 = 52.000.000 VND + 10% VAT (5.200.000) = 57.200.000 VND
    assert tco_b.total_tco == Decimal("57200000.00")

    # BƯỚC 3: compare_suppliers
    state_cmp = {**state_tco, **compare_suppliers_node(state_tco)}
    matrix = state_cmp["comparison_matrix"]
    assert isinstance(matrix, SupplierComparisonMatrix)
    assert set(matrix.suppliers) == {"NCC Toàn Cầu (Mỹ)", "NCC Hà Nội"}
    assert matrix.means["total_tco"] == Decimal("54000000.00")
    assert matrix.means["lead_time_days"] == Decimal("12.5")
    assert matrix.means["warranty_months"] == Decimal("18")

    # NCC A rẻ hơn giá trung bình -> deviation_pct âm
    cell_tco_a = matrix.matrix["NCC Toàn Cầu (Mỹ)"]["total_tco"]
    assert cell_tco_a.deviation_pct is not None
    assert cell_tco_a.deviation_pct < 0


def test_tc_flow06_full_e2e_seven_nodes_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chuỗi End-to-End toàn diện 7 node từ PDF đến Ma trận so sánh NCC và Rủi ro."""
    doc_a = tmp_path / "supplier_a.pdf"
    doc_b = tmp_path / "supplier_b.pdf"
    doc_a.write_bytes(b"%PDF-1.7 Supplier A Quote")
    doc_b.write_bytes(b"%PDF-1.7 Supplier B Quote")

    class MultiDocOCRClient:
        def extract_text(self, document_path: str) -> str:
            return f"OCR Text for {Path(document_path).name}"

    class MultiDocExtractionClient:
        def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, Any]]:
            if "supplier_a" in document_path:
                return [
                    {
                        "supplier_name": "Công ty Alpha",
                        "currency": "vnd",
                        "product_name": "Bàn làm việc",
                        "unit": "cái",
                        "quantity": "10",
                        "unit_price": "1000000.00",
                        "page_number": 1,
                        "confidence_score": 0.95,
                    }
                ]
            return [
                {
                    "supplier_name": "Công ty Beta",
                    "currency": "vnd",
                    "product_name": "Bàn làm việc",
                    "unit": "cái",
                    "quantity": "10",
                    "unit_price": "1200000.00",
                    "page_number": 1,
                    "confidence_score": 0.95,
                }
            ]

    # Node 1: extract_documents
    state_1 = extract_documents(
        {"documents": [str(doc_a), str(doc_b)]},
        ocr_client=MultiDocOCRClient(),
        extraction_client=MultiDocExtractionClient(),
    )
    assert len(state_1["raw_extractions"]) == 2

    # Node 2: validate_extraction
    state_2 = {**state_1, **validate_extraction(state_1)}
    assert all(val.schema_valid for val in state_2["validated_extractions"])

    # Node 3: human_review_extraction (HITL-1)
    buyer_response = [
        {
            "supplier_name": "Công ty Alpha",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 7,
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][0]["items"][0]["source_item_id"],
                    "product_name": "Bàn làm việc",
                    "unit": "cái",
                    "quantity": "10",
                    "unit_price": "1000000.00",
                }
            ],
        },
        {
            "supplier_name": "Công ty Beta",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 14,
            "warranty_months": 24,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][1]["items"][0]["source_item_id"],
                    "product_name": "Bàn làm việc",
                    "unit": "cái",
                    "quantity": "10",
                    "unit_price": "1200000.00",
                }
            ],
        },
    ]
    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=buyer_response))
    state_3 = {**state_2, **human_review_extraction(state_2)}

    # Node 4: normalize
    due_date = (date.today() + timedelta(days=30)).isoformat()
    state_3["pr_data"] = {
        "target_uom": "cái",
        "target_currency": "VND",
        "delivery_due_date": due_date,
    }
    state_4 = {**state_3, **normalize(state_3)}

    # Node 5 & Node 6 (Chạy song song trong pha phân tích): calculate_tco và analyze_risks
    state_5 = {
        **state_4,
        **calculate_tco_node(state_4),
        **analyze_risks_node(state_4),
    }

    # Node 7: compare_suppliers
    state_final = {**state_5, **compare_suppliers_node(state_5)}

    # Khẳng định ở biên cuối cùng
    assert state_final["risk_flags"] == []
    matrix = state_final["comparison_matrix"]
    assert set(matrix.suppliers) == {"Công ty Alpha", "Công ty Beta"}
    assert matrix.means["total_tco"] == Decimal("11000000.00")
    assert matrix.means["lead_time_days"] == Decimal("10.5")
    assert matrix.means["warranty_months"] == Decimal("18")


def test_tc_flow07_chain_risk_detection_lead_time_exceeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Toàn luồng: Phát hiện rủi ro thời hạn giao hàng vượt deadline PR."""
    doc_a = tmp_path / "quote_fast.pdf"
    doc_b = tmp_path / "quote_slow.pdf"
    doc_a.write_bytes(b"%PDF-1.7 Fast Supplier")
    doc_b.write_bytes(b"%PDF-1.7 Slow Supplier")

    class MultiDocOCRClient:
        def extract_text(self, document_path: str) -> str:
            return "OCR Content"

    class MultiDocExtractionClient:
        def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, Any]]:
            if "quote_fast" in document_path:
                return [
                    {
                        "supplier_name": "NCC Nhanh",
                        "currency": "vnd",
                        "product_name": "Ghế xoay",
                        "unit": "cái",
                        "quantity": "5",
                        "unit_price": "500000.00",
                        "page_number": 1,
                        "confidence_score": 0.95,
                    }
                ]
            return [
                {
                    "supplier_name": "NCC Chậm",
                    "currency": "vnd",
                    "product_name": "Ghế xoay",
                    "unit": "cái",
                    "quantity": "5",
                    "unit_price": "450000.00",
                    "page_number": 1,
                    "confidence_score": 0.95,
                }
            ]

    # Node 1: extract_documents
    state_1 = extract_documents(
        {"documents": [str(doc_a), str(doc_b)]},
        ocr_client=MultiDocOCRClient(),
        extraction_client=MultiDocExtractionClient(),
    )

    # Node 2: validate_extraction
    state_2 = {**state_1, **validate_extraction(state_1)}

    # Node 3: human_review_extraction (HITL-1)
    # NCC Nhanh giao trong 5 ngày; NCC Chậm giao trong 25 ngày
    buyer_response = [
        {
            "supplier_name": "NCC Nhanh",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 5,
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][0]["items"][0]["source_item_id"],
                    "product_name": "Ghế xoay",
                    "unit": "cái",
                    "quantity": "5",
                    "unit_price": "500000.00",
                }
            ],
        },
        {
            "supplier_name": "NCC Chậm",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 25,  # Chậm trễ đáng kể
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][1]["items"][0]["source_item_id"],
                    "product_name": "Ghế xoay",
                    "unit": "cái",
                    "quantity": "5",
                    "unit_price": "450000.00",
                }
            ],
        },
    ]
    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=buyer_response))
    state_3 = {**state_2, **human_review_extraction(state_2)}

    # Node 4: normalize
    # Deadline PR: chỉ còn 7 ngày kể từ hôm nay
    deadline_date = (date.today() + timedelta(days=7)).isoformat()
    state_3["pr_data"] = {
        "target_uom": "cái",
        "target_currency": "VND",
        "delivery_due_date": deadline_date,
    }
    state_4 = {**state_3, **normalize(state_3)}

    # Node 5 & 6: calculate_tco và analyze_risks
    state_5 = {
        **state_4,
        **calculate_tco_node(state_4),
        **analyze_risks_node(state_4),
    }

    # Node 7: compare_suppliers
    state_final = {**state_5, **compare_suppliers_node(state_5)}

    # Khẳng định ở biên cuối cùng:
    # 1. TCO và Ma trận vẫn được tính đầy đủ cho cả 2 NCC
    assert len(state_final["tco_results"]) == 2
    assert set(state_final["comparison_matrix"].suppliers) == {"NCC Nhanh", "NCC Chậm"}

    # 2. Rủi ro được phát hiện và cảnh báo chính xác cho NCC Chậm
    assert len(state_final["risk_flags"]) == 1
    risk = state_final["risk_flags"][0]
    assert risk.supplier_id == "NCC Chậm"
    assert risk.risk_type == "lead_time_exceeded"
    assert risk.severity == RiskSeverity.HIGH
    assert risk.details["lead_time_days"] == 25


# ==============================================================================
# Helper & Stub cho decision_llm Boundary Tests
# ==============================================================================
class StubBoundaryDecisionModel:
    def __init__(self, response: str | dict[str, Any]) -> None:
        self.response = response
        self.call_count = 0
        self.last_messages: list[dict[str, Any]] | None = None

    def invoke(self, messages: list[dict[str, Any]]) -> str | dict[str, Any]:
        self.call_count += 1
        self.last_messages = messages
        return self.response


def _make_boundary_tco(
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


# --- 6. decision_llm single-node boundary (TC-B17 -> TC-B20) ---
def test_tc_b17_decision_llm_valid_tco_and_matrix_proposed() -> None:
    """TC-B17: TCO hợp lệ + Ma trận so sánh -> Đề xuất PROPOSED ở biên."""
    tco_a = _make_boundary_tco("NCC A", "10000000", revision_id="rev_a")
    tco_b = _make_boundary_tco("NCC B", "12000000", revision_id="rev_b")
    matrix = SupplierComparisonMatrix(
        suppliers=["NCC A", "NCC B"],
        criteria=["total_tco"],
        matrix={"NCC A": {}, "NCC B": {}},
        means={"total_tco": Decimal("11000000")},
    )
    stub_llm = StubBoundaryDecisionModel(
        {
            "status": "proposed",
            "preferred_supplier_id": "NCC A",
            "ranked_supplier_ids": ["NCC A", "NCC B"],
            "rationale": "NCC A có TCO thấp nhất.",
            "tradeoffs": [
                {
                    "preferred_supplier_id": "NCC A",
                    "alternative_supplier_id": "NCC B",
                    "description": "NCC A rẻ hơn 2 triệu VND.",
                }
            ],
        }
    )
    state = {
        "tco_results": [tco_a, tco_b],
        "comparison_matrix": matrix,
        "risk_flags": [],
        "pr_data": {"top_n": 2},
    }
    result = decision_llm(state, llm=stub_llm)
    prop = result["decision_proposal"]
    assert prop.status == DecisionProposalStatus.PROPOSED
    assert prop.preferred_supplier_id == "NCC A"
    assert prop.ranked_supplier_ids == ["NCC A", "NCC B"]
    assert prop.input_artifact_ids == ["rev_a", "rev_b"]


def test_tc_b18_decision_llm_empty_tco_early_exit_needs_input() -> None:
    """TC-B18: Dữ liệu TCO rỗng hoặc toàn bộ MISSING_DATA -> Thoát sớm NEEDS_INPUT."""
    matrix = SupplierComparisonMatrix(suppliers=[], criteria=[], matrix={}, means={})
    stub_llm = StubBoundaryDecisionModel("{}")
    state = {"tco_results": [], "comparison_matrix": matrix}
    result = decision_llm(state, llm=stub_llm)
    prop = result["decision_proposal"]
    assert prop.status == DecisionProposalStatus.NEEDS_INPUT
    assert prop.preferred_supplier_id is None
    assert prop.rationale == "Không có nhà cung cấp đủ dữ liệu TCO để xếp hạng."
    assert stub_llm.call_count == 0


def test_tc_b19_decision_llm_missing_matrix_early_exit_needs_input() -> None:
    """TC-B19: Thiếu comparison_matrix -> Thoát sớm NEEDS_INPUT."""
    tco_a = _make_boundary_tco("NCC A")
    stub_llm = StubBoundaryDecisionModel("{}")
    state = {"tco_results": [tco_a], "comparison_matrix": None}
    result = decision_llm(state, llm=stub_llm)
    prop = result["decision_proposal"]
    assert prop.status == DecisionProposalStatus.NEEDS_INPUT
    assert prop.preferred_supplier_id is None
    assert prop.rationale == "Thiếu ma trận so sánh nhà cung cấp."
    assert stub_llm.call_count == 0


def test_tc_b20_decision_llm_markdown_fence_decode_and_artifact_enforcement() -> None:
    """TC-B20: Đầu ra dạng Markdown Code Block -> Bóc tách và chuẩn hóa artifact IDs."""
    tco_a = _make_boundary_tco("NCC A", revision_id="real_rev_a")
    tco_b = _make_boundary_tco("NCC B", revision_id="real_rev_b")
    matrix = SupplierComparisonMatrix(suppliers=["NCC A", "NCC B"], criteria=[], matrix={}, means={})
    fence_json = (
        "```json\n"
        "{\n"
        '  "status": "proposed",\n'
        '  "preferred_supplier_id": "NCC A",\n'
        '  "ranked_supplier_ids": ["NCC A", "NCC B"],\n'
        '  "rationale": "Chọn A.",\n'
        '  "tradeoffs": [],\n'
        '  "input_artifact_ids": ["bogus_id_999"]\n'
        "}\n"
        "```"
    )
    stub_llm = StubBoundaryDecisionModel(fence_json)
    state = {"tco_results": [tco_a, tco_b], "comparison_matrix": matrix, "pr_data": {"top_n": 2}}
    result = decision_llm(state, llm=stub_llm)
    prop = result["decision_proposal"]
    assert prop.status == DecisionProposalStatus.PROPOSED
    assert prop.preferred_supplier_id == "NCC A"
    assert prop.input_artifact_ids == ["real_rev_a", "real_rev_b"]


# ==============================================================================
# Full End-to-End 8 Nodes Pipeline (TC-FLOW-08 -> TC-FLOW-10)
# ==============================================================================
def test_tc_flow08_full_e2e_eight_nodes_chain_to_decision_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-FLOW-08: Chuỗi Toàn Luồng 8 Node — Đề Xuất Quyết Định Hoàn Chỉnh."""
    doc_a = tmp_path / "quote_flow8_a.pdf"
    doc_b = tmp_path / "quote_flow8_b.pdf"
    doc_a.write_bytes(b"%PDF-1.7 flow8 a")
    doc_b.write_bytes(b"%PDF-1.7 flow8 b")

    class MultiDocOCRClient:
        def extract_text(self, document_path: str) -> str:
            return "text"

    class MultiDocExtractionClient:
        def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, Any]]:
            if "quote_flow8_a" in document_path:
                return [
                    {
                        "supplier_name": "Supplier A",
                        "currency": "vnd",
                        "product_name": "Bàn làm việc",
                        "unit": "cái",
                        "quantity": "2",
                        "unit_price": "1000000.00",
                        "page_number": 1,
                        "confidence_score": 0.95,
                    }
                ]
            return [
                {
                    "supplier_name": "Supplier B",
                    "currency": "vnd",
                    "product_name": "Bàn làm việc",
                    "unit": "cái",
                    "quantity": "2",
                    "unit_price": "1200000.00",
                    "page_number": 1,
                    "confidence_score": 0.95,
                }
            ]

    # Node 1: extract_documents
    state_0: dict[str, Any] = {"documents": [str(doc_a), str(doc_b)]}
    state_1 = {
        **state_0,
        **extract_documents(
            state_0,
            ocr_client=MultiDocOCRClient(),
            extraction_client=MultiDocExtractionClient(),
        ),
    }

    # Node 2: validate_extraction
    state_2 = {**state_1, **validate_extraction(state_1)}

    # Node 3: human_review_extraction (HITL-1)
    buyer_response = [
        {
            "supplier_name": "Supplier A",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 3,
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][0]["items"][0]["source_item_id"],
                    "product_name": "Bàn làm việc",
                    "unit": "cái",
                    "quantity": "2",
                    "unit_price": "1000000.00",
                }
            ],
        },
        {
            "supplier_name": "Supplier B",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 5,
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][1]["items"][0]["source_item_id"],
                    "product_name": "Bàn làm việc",
                    "unit": "cái",
                    "quantity": "2",
                    "unit_price": "1200000.00",
                }
            ],
        },
    ]
    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=buyer_response))
    state_3 = {**state_2, **human_review_extraction(state_2)}

    # Node 4: normalize
    deadline_date = (date.today() + timedelta(days=20)).isoformat()
    state_3["pr_data"] = {
        "target_uom": "cái",
        "target_currency": "VND",
        "delivery_due_date": deadline_date,
        "top_n": 2,
    }
    state_4 = {**state_3, **normalize(state_3)}

    # Node 5 & 6: calculate_tco và analyze_risks
    state_5 = {
        **state_4,
        **calculate_tco_node(state_4),
        **analyze_risks_node(state_4),
    }

    # Node 7: compare_suppliers
    state_6 = {**state_5, **compare_suppliers_node(state_5)}

    # Node 8: decision_llm
    stub_llm = StubBoundaryDecisionModel(
        {
            "status": "proposed",
            "preferred_supplier_id": "Supplier A",
            "ranked_supplier_ids": ["Supplier A", "Supplier B"],
            "rationale": "Supplier A có tổng chi phí thấp hơn.",
            "tradeoffs": [
                {
                    "preferred_supplier_id": "Supplier A",
                    "alternative_supplier_id": "Supplier B",
                    "description": "Supplier A tiết kiệm chi phí hơn Supplier B.",
                }
            ],
        }
    )
    state_final = {**state_6, **decision_llm(state_6, llm=stub_llm)}

    # Assert ở biên cuối cùng:
    assert "decision_proposal" in state_final
    prop = state_final["decision_proposal"]
    assert prop.status == DecisionProposalStatus.PROPOSED
    assert prop.preferred_supplier_id == "Supplier A"
    assert prop.ranked_supplier_ids == ["Supplier A", "Supplier B"]
    assert len(prop.input_artifact_ids) == 2


def test_tc_flow09_eight_nodes_chain_risk_detection_fed_to_decision_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-FLOW-09: Chuỗi 8 Node Tích Hợp Rủi Ro vào Đề Xuất Quyết Định."""
    doc_fast = tmp_path / "quote_flow9_fast.pdf"
    doc_slow = tmp_path / "quote_flow9_slow.pdf"
    doc_fast.write_bytes(b"%PDF-1.7 fast")
    doc_slow.write_bytes(b"%PDF-1.7 slow")

    class MultiDocOCRClient:
        def extract_text(self, document_path: str) -> str:
            return "text"

    class MultiDocExtractionClient:
        def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, Any]]:
            if "fast" in document_path:
                return [
                    {
                        "supplier_name": "NCC Nhanh",
                        "currency": "vnd",
                        "product_name": "Cáp mạng",
                        "unit": "cái",
                        "quantity": "10",
                        "unit_price": "60000.00",
                        "page_number": 1,
                        "confidence_score": 0.95,
                    }
                ]
            return [
                {
                    "supplier_name": "NCC Chậm",
                    "currency": "vnd",
                    "product_name": "Cáp mạng",
                    "unit": "cái",
                    "quantity": "10",
                    "unit_price": "50000.00",
                    "page_number": 1,
                    "confidence_score": 0.95,
                }
            ]

    # Node 1 -> 3
    state_1 = extract_documents(
        {"documents": [str(doc_fast), str(doc_slow)]},
        ocr_client=MultiDocOCRClient(),
        extraction_client=MultiDocExtractionClient(),
    )
    state_2 = {**state_1, **validate_extraction(state_1)}

    buyer_response = [
        {
            "supplier_name": "NCC Nhanh",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 4,
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][0]["items"][0]["source_item_id"],
                    "product_name": "Cáp mạng",
                    "unit": "cái",
                    "quantity": "10",
                    "unit_price": "60000.00",
                }
            ],
        },
        {
            "supplier_name": "NCC Chậm",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 20,
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][1]["items"][0]["source_item_id"],
                    "product_name": "Cáp mạng",
                    "unit": "cái",
                    "quantity": "10",
                    "unit_price": "50000.00",
                }
            ],
        },
    ]
    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=buyer_response))
    state_3 = {**state_2, **human_review_extraction(state_2)}

    # Deadline PR chỉ còn 5 ngày làm việc
    deadline_date = (date.today() + timedelta(days=5)).isoformat()
    state_3["pr_data"] = {
        "target_uom": "cái",
        "target_currency": "VND",
        "delivery_due_date": deadline_date,
        "top_n": 2,
    }
    state_4 = {**state_3, **normalize(state_3)}

    state_5 = {
        **state_4,
        **calculate_tco_node(state_4),
        **analyze_risks_node(state_4),
    }
    state_6 = {**state_5, **compare_suppliers_node(state_5)}

    # Stub LLM nhận diện cờ rủi ro và chọn NCC Nhanh
    stub_llm = StubBoundaryDecisionModel(
        {
            "status": "proposed",
            "preferred_supplier_id": "NCC Nhanh",
            "ranked_supplier_ids": ["NCC Nhanh", "NCC Chậm"],
            "rationale": "Chọn NCC Nhanh do NCC Chậm bị rủi ro giao hàng trễ 15 ngày so với deadline PR.",
            "tradeoffs": [
                {
                    "preferred_supplier_id": "NCC Nhanh",
                    "alternative_supplier_id": "NCC Chậm",
                    "description": "Giá cao hơn một chút nhưng đảm bảo tiến độ vận hành.",
                }
            ],
        }
    )
    state_final = {**state_6, **decision_llm(state_6, llm=stub_llm)}

    # Assert ở biên:
    assert {risk.supplier_id for risk in state_final["risk_flags"]} == {"NCC Nhanh", "NCC Chậm"}

    # User message gửi tới LLM phải chứa risk_flags
    assert stub_llm.last_messages is not None
    user_payload = json.loads(stub_llm.last_messages[1]["content"])
    assert {risk["supplier_id"] for risk in user_payload["risk_flags"]} == {"NCC Nhanh", "NCC Chậm"}

    prop = state_final["decision_proposal"]
    assert prop.status == DecisionProposalStatus.PROPOSED
    assert prop.preferred_supplier_id == "NCC Nhanh"
    assert "trễ" in prop.rationale


def test_tc_flow10_eight_nodes_incompatible_uom_early_exit_needs_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-FLOW-10: Chuỗi 8 Node Lệch Chuẩn Hóa Dẫn đến Thoát Sớm tại Decision LLM."""
    doc_steel = tmp_path / "quote_flow10_steel.pdf"
    doc_steel.write_bytes(b"%PDF-1.7 steel")

    state_1 = extract_documents(
        {"documents": [str(doc_steel)]},
        ocr_client=StubOCRClient("steel ocr"),
        extraction_client=StubExtractionClient(
            [
                {
                    "supplier_name": "NCC Thép",
                    "currency": "vnd",
                    "product_name": "Thép cuộn",
                    "unit": "kg",
                    "quantity": "50",
                    "unit_price": "20000.00",
                    "page_number": 1,
                    "confidence_score": 0.95,
                }
            ]
        ),
    )
    state_2 = {**state_1, **validate_extraction(state_1)}

    buyer_response = [
        {
            "supplier_name": "NCC Thép",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 3,
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][0]["items"][0]["source_item_id"],
                    "product_name": "Thép cuộn",
                    "unit": "kg",
                    "quantity": "50",
                    "unit_price": "20000.00",
                }
            ],
        }
    ]
    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=buyer_response))
    state_3 = {**state_2, **human_review_extraction(state_2)}

    # PR yêu cầu target_uom="cái", nhưng báo giá là "kg" (không quy đổi tự động được)
    state_3["pr_data"] = {
        "target_uom": "cái",
        "target_currency": "VND",
    }
    state_4 = {**state_3, **normalize(state_3)}
    state_5 = {
        **state_4,
        **calculate_tco_node(state_4),
        **analyze_risks_node(state_4),
    }
    state_6 = {**state_5, **compare_suppliers_node(state_5)}

    stub_llm = StubBoundaryDecisionModel("{}")
    state_final = {**state_6, **decision_llm(state_6, llm=stub_llm)}

    # Assert ở biên:
    # 1. Normalize đánh dấu NEEDS_MAPPING
    assert state_final["normalized_quotes"][0].status == NormalizationStatus.NEEDS_MAPPING
    # 2. TCO đánh dấu MISSING_DATA
    assert state_final["tco_results"][0].status == TCOCalculationStatus.MISSING_DATA
    # 3. Decision LLM tự phát hiện và thoát sớm NEEDS_INPUT không gọi LLM
    prop = state_final["decision_proposal"]
    assert prop.status == DecisionProposalStatus.NEEDS_INPUT
    assert prop.preferred_supplier_id is None
    assert prop.rationale == "Không có nhà cung cấp đủ dữ liệu TCO để xếp hạng."
    assert stub_llm.call_count == 0


# ==============================================================================
# Single-Node Boundary: human_review_recommendation (HITL-2) & Router (TC-B21 -> TC-B24)
# ==============================================================================
def test_tc_b21_human_review_recommendation_submit_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-B21: Buyer Duyệt Đề Xuất -> action = SUBMIT."""
    proposal = DecisionProposal(
        status=DecisionProposalStatus.PROPOSED,
        preferred_supplier_id="NCC A",
        ranked_supplier_ids=["NCC A", "NCC B"],
        rationale="Tối ưu.",
        tradeoffs=[],
        input_artifact_ids=["rev-1"],
    )
    matrix = SupplierComparisonMatrix(suppliers=["NCC A", "NCC B"], criteria=[], matrix={}, means={})
    state = {
        "decision_proposal": proposal,
        "comparison_matrix": matrix,
        "analysis_revision": 1,
    }

    buyer_response = {
        "analysis_revision": 1,
        "action": "submit",
        "note": "Đồng ý đề xuất",
    }
    monkeypatch.setattr(_hrr_mod, "interrupt", MagicMock(return_value=buyer_response))

    result = human_review_recommendation(state)
    assert "buyer_approval_request" in result
    req = result["buyer_approval_request"]
    assert req.action == BuyerAction.SUBMIT
    assert req.analysis_revision == 1
    assert req.note == "Đồng ý đề xuất"


def test_tc_b22_human_review_recommendation_revise_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-B22: Buyer Yêu Cầu Chỉnh Sửa -> action = REVISE kèm ghi chú."""
    proposal = DecisionProposal(
        status=DecisionProposalStatus.PROPOSED,
        preferred_supplier_id="NCC A",
        ranked_supplier_ids=["NCC A", "NCC B"],
        rationale="Tối ưu.",
        tradeoffs=[],
    )
    matrix = SupplierComparisonMatrix(suppliers=["NCC A", "NCC B"], criteria=[], matrix={}, means={})
    state = {
        "decision_proposal": proposal,
        "comparison_matrix": matrix,
        "analysis_revision": 1,
    }

    buyer_response = {
        "analysis_revision": 1,
        "action": "revise",
        "note": "Yêu cầu đàm phán lại giá với Beta",
    }
    monkeypatch.setattr(_hrr_mod, "interrupt", MagicMock(return_value=buyer_response))

    result = human_review_recommendation(state)
    req = result["buyer_approval_request"]
    assert req.action == BuyerAction.REVISE
    assert req.note == "Yêu cầu đàm phán lại giá với Beta"


def test_tc_b23_human_review_recommendation_revision_mismatch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-B23: Sai Lệch Phiên Phê Duyệt -> AnalysisRevisionMismatchError."""
    proposal = DecisionProposal(
        status=DecisionProposalStatus.PROPOSED,
        preferred_supplier_id="NCC A",
        ranked_supplier_ids=["NCC A", "NCC B"],
        rationale="Tối ưu.",
    )
    matrix = SupplierComparisonMatrix(suppliers=["NCC A", "NCC B"], criteria=[], matrix={}, means={})
    # State hiện tại revision 2 nhưng Buyer gửi về revision 1
    state = {
        "decision_proposal": proposal,
        "comparison_matrix": matrix,
        "analysis_revision": 2,
    }

    buyer_response = {
        "analysis_revision": 1,
        "action": "submit",
    }
    monkeypatch.setattr(_hrr_mod, "interrupt", MagicMock(return_value=buyer_response))

    with pytest.raises(AnalysisRevisionMismatchError) as exc_info:
        human_review_recommendation(state)
    assert exc_info.value.expected == 2
    assert exc_info.value.actual == 1


def test_tc_b24_buyer_decision_router_all_branches() -> None:
    """TC-B24: Định tuyến Quyết Định buyer_decision_router."""
    req_sub = BuyerSubmitApprovalRequest(analysis_revision=1, action=BuyerAction.SUBMIT)
    assert buyer_decision_router({"buyer_approval_request": req_sub}) == "submit"

    req_rev = BuyerSubmitApprovalRequest(analysis_revision=1, action=BuyerAction.REVISE, note="Sửa lại")
    assert buyer_decision_router({"buyer_approval_request": req_rev}) == "revise"

    assert buyer_decision_router({}) == "invalid"
    assert buyer_decision_router({"buyer_approval_request": None}) == "invalid"


# ==============================================================================
# Full End-to-End 9 Nodes Pipeline (TC-FLOW-11 -> TC-FLOW-12)
# ==============================================================================
def test_tc_flow11_full_e2e_nine_nodes_chain_to_submit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-FLOW-11: Chuỗi Toàn Luồng 9 Node — Buyer Phê Duyệt Trình Manager Duyệt."""
    doc_a = tmp_path / "quote_flow11_a.pdf"
    doc_b = tmp_path / "quote_flow11_b.pdf"
    doc_a.write_bytes(b"%PDF-1.7 flow11 a")
    doc_b.write_bytes(b"%PDF-1.7 flow11 b")

    class MultiDocOCRClient:
        def extract_text(self, document_path: str) -> str:
            return "text"

    class MultiDocExtractionClient:
        def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, Any]]:
            if "quote_flow11_a" in document_path:
                return [
                    {
                        "supplier_name": "Supplier A",
                        "currency": "vnd",
                        "product_name": "Máy tính bảng",
                        "unit": "cái",
                        "quantity": "2",
                        "unit_price": "5000000.00",
                        "page_number": 1,
                        "confidence_score": 0.95,
                    }
                ]
            return [
                {
                    "supplier_name": "Supplier B",
                    "currency": "vnd",
                    "product_name": "Máy tính bảng",
                    "unit": "cái",
                    "quantity": "2",
                    "unit_price": "5500000.00",
                    "page_number": 1,
                    "confidence_score": 0.95,
                }
            ]

    # Node 1 -> 3
    state_0: dict[str, Any] = {"documents": [str(doc_a), str(doc_b)]}
    state_1 = {
        **state_0,
        **extract_documents(
            state_0,
            ocr_client=MultiDocOCRClient(),
            extraction_client=MultiDocExtractionClient(),
        ),
    }
    state_2 = {**state_1, **validate_extraction(state_1)}

    buyer_response_hitl1 = [
        {
            "supplier_name": "Supplier A",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 3,
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][0]["items"][0]["source_item_id"],
                    "product_name": "Máy tính bảng",
                    "unit": "cái",
                    "quantity": "2",
                    "unit_price": "5000000.00",
                }
            ],
        },
        {
            "supplier_name": "Supplier B",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 5,
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][1]["items"][0]["source_item_id"],
                    "product_name": "Máy tính bảng",
                    "unit": "cái",
                    "quantity": "2",
                    "unit_price": "5500000.00",
                }
            ],
        },
    ]
    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=buyer_response_hitl1))
    state_3 = {**state_2, **human_review_extraction(state_2)}

    # Node 4 -> 7
    deadline_date = (date.today() + timedelta(days=20)).isoformat()
    state_3["pr_data"] = {
        "target_uom": "cái",
        "target_currency": "VND",
        "delivery_due_date": deadline_date,
        "top_n": 2,
    }
    state_4 = {**state_3, **normalize(state_3)}
    state_5 = {
        **state_4,
        **calculate_tco_node(state_4),
        **analyze_risks_node(state_4),
    }
    state_6 = {**state_5, **compare_suppliers_node(state_5)}

    # Node 8: decision_llm
    stub_llm = StubBoundaryDecisionModel(
        {
            "status": "proposed",
            "preferred_supplier_id": "Supplier A",
            "ranked_supplier_ids": ["Supplier A", "Supplier B"],
            "rationale": "Supplier A tối ưu chi phí hơn.",
            "tradeoffs": [],
        }
    )
    state_7 = {**state_6, **decision_llm(state_6, llm=stub_llm)}

    # Node 9: human_review_recommendation (HITL-2)
    buyer_response_hitl2 = {
        "analysis_revision": 1,
        "action": "submit",
        "note": "Nhất trí chọn NCC A",
    }
    monkeypatch.setattr(_hrr_mod, "interrupt", MagicMock(return_value=buyer_response_hitl2))
    state_final = {**state_7, **human_review_recommendation(state_7)}

    # Router quyết định bước tiếp theo
    route_decision = buyer_decision_router(state_final)

    # Assert ở biên cuối cùng:
    assert state_final["decision_proposal"].status == DecisionProposalStatus.PROPOSED
    assert state_final["decision_proposal"].preferred_supplier_id == "Supplier A"
    assert state_final["buyer_approval_request"].action == BuyerAction.SUBMIT
    assert state_final["buyer_approval_request"].note == "Nhất trí chọn NCC A"
    assert route_decision == "submit"


def test_tc_flow12_full_e2e_nine_nodes_chain_to_revise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-FLOW-12: Chuỗi Toàn Luồng 9 Node — Buyer Yêu Cầu Chỉnh Sửa Đề Xuất."""
    doc_a = tmp_path / "quote_flow12_a.pdf"
    doc_b = tmp_path / "quote_flow12_b.pdf"
    doc_a.write_bytes(b"%PDF-1.7 flow12 a")
    doc_b.write_bytes(b"%PDF-1.7 flow12 b")

    class MultiDocOCRClient:
        def extract_text(self, document_path: str) -> str:
            return "text"

    class MultiDocExtractionClient:
        def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, Any]]:
            return [
                {
                    "supplier_name": "Supplier A" if "flow12_a" in document_path else "Supplier B",
                    "currency": "vnd",
                    "product_name": "Màn hình",
                    "unit": "cái",
                    "quantity": "1",
                    "unit_price": "3000000.00",
                    "page_number": 1,
                    "confidence_score": 0.95,
                }
            ]

    # Node 1 -> 3
    state_0: dict[str, Any] = {"documents": [str(doc_a), str(doc_b)]}
    state_1 = {
        **state_0,
        **extract_documents(
            state_0,
            ocr_client=MultiDocOCRClient(),
            extraction_client=MultiDocExtractionClient(),
        ),
    }
    state_2 = {**state_1, **validate_extraction(state_1)}

    buyer_response_hitl1 = [
        {
            "supplier_name": "Supplier A",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 3,
            "warranty_months": 12,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][0]["items"][0]["source_item_id"],
                    "product_name": "Màn hình",
                    "unit": "cái",
                    "quantity": "1",
                    "unit_price": "3000000.00",
                }
            ],
        },
        {
            "supplier_name": "Supplier B",
            "currency": "VND",
            "vat_rate": "0.10",
            "vat_included": True,
            "lead_time_days": 4,
            "warranty_months": 24,
            "payment_terms": "net 30",
            "items": [
                {
                    "source_item_id": state_1["raw_extractions"][1]["items"][0]["source_item_id"],
                    "product_name": "Màn hình",
                    "unit": "cái",
                    "quantity": "1",
                    "unit_price": "3200000.00",
                }
            ],
        },
    ]
    monkeypatch.setattr(_hitl_mod, "interrupt", MagicMock(return_value=buyer_response_hitl1))
    state_3 = {**state_2, **human_review_extraction(state_2)}

    # Node 4 -> 7
    deadline_date = (date.today() + timedelta(days=20)).isoformat()
    state_3["pr_data"] = {
        "target_uom": "cái",
        "target_currency": "VND",
        "delivery_due_date": deadline_date,
        "top_n": 2,
    }
    state_4 = {**state_3, **normalize(state_3)}
    state_5 = {
        **state_4,
        **calculate_tco_node(state_4),
        **analyze_risks_node(state_4),
    }
    state_6 = {**state_5, **compare_suppliers_node(state_5)}

    # Node 8: decision_llm đề xuất Supplier A
    stub_llm = StubBoundaryDecisionModel(
        {
            "status": "proposed",
            "preferred_supplier_id": "Supplier A",
            "ranked_supplier_ids": ["Supplier A", "Supplier B"],
            "rationale": "Supplier A rẻ hơn 200k.",
            "tradeoffs": [],
        }
    )
    state_7 = {**state_6, **decision_llm(state_6, llm=stub_llm)}

    # Node 9: Buyer tại HITL-2 yêu cầu đàm phán thêm bảo hành (REVISE)
    buyer_response_hitl2 = {
        "analysis_revision": 1,
        "action": "revise",
        "note": "Cần đàm phán Supplier A nâng bảo hành lên 24 tháng bằng Supplier B",
    }
    monkeypatch.setattr(_hrr_mod, "interrupt", MagicMock(return_value=buyer_response_hitl2))
    state_final = {**state_7, **human_review_recommendation(state_7)}

    route_decision = buyer_decision_router(state_final)

    # Assert ở biên:
    assert state_final["buyer_approval_request"].action == BuyerAction.REVISE
    assert "24 tháng" in (state_final["buyer_approval_request"].note or "")
    assert route_decision == "revise"
