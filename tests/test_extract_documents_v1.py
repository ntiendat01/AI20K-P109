from __future__ import annotations

import json
from pathlib import Path

from src.agents.nodes.extract_documents import extract_documents
from src.domain.agent.quotation.extraction import ExtractionDraftPayload


class FakeOCRClient:
    def __init__(self, text: str = "readable OCR text") -> None:
        self.text = text

    def extract_text(self, document_path: str) -> str:
        del document_path
        return self.text


class FakeExtractionClient:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self.items = items

    def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, object]]:
        del ocr_text, document_path
        return self.items


def test_extract_documents_returns_agent_contract_draft(tmp_path: Path) -> None:
    document = tmp_path / "quote.pdf"
    document.write_bytes(b"%PDF-1.7 fixture")
    first_item: dict[str, object] = {
        "supplier": "Supplier A",
        "item_name": "Laptop",
        "product_code": "LT-01",
        "unit": "piece",
        "quantity": 10,
        "unit_price": 15_000_000,
        "currency": "vnd",
        "vat_rate": 0.1,
        "vat_included": False,
        "lead_time_days": 7,
        "warranty_months": 12,
        "payment_terms": "30 days",
        "page_number": 2,
        "confidence_score": 0.91,
        "field_confidence": {"item_name": 0.96, "unit_price": 0.74},
    }

    result = extract_documents(
        {"documents": [str(document)]},
        ocr_client=FakeOCRClient(),
        extraction_client=FakeExtractionClient([first_item, dict(first_item)]),
    )

    draft = ExtractionDraftPayload.model_validate(result["raw_extractions"][0])
    assert draft.supplier_name is not None
    assert draft.supplier_name.value == "Supplier A"
    assert draft.currency is not None
    assert draft.currency.value == "VND"
    assert draft.vat_included is not None
    assert draft.vat_included.value == "false"
    assert len(draft.items) == 1
    assert draft.items[0].product_name.value == "Laptop"
    assert str(draft.items[0].product_name.confidence) == "0.96"
    assert draft.items[0].product_name.source is not None
    assert draft.items[0].product_name.source.page_number == 2
    assert str(draft.items[0].unit_price.confidence) == "0.74"


def test_extract_documents_returns_empty_v1_draft_for_unreadable_document(tmp_path: Path) -> None:
    document = tmp_path / "unreadable.pdf"
    document.write_bytes(b"%PDF-1.7 fixture")

    result = extract_documents(
        {"documents": [str(document)]},
        ocr_client=FakeOCRClient(""),
        extraction_client=FakeExtractionClient([]),
    )

    draft = ExtractionDraftPayload.model_validate(result["raw_extractions"][0])
    assert draft == ExtractionDraftPayload()


def test_extract_documents_uses_ocr_confidence_in_parsed_json(tmp_path: Path) -> None:
    document = tmp_path / "quote.pdf"
    document.write_bytes(b"%PDF-1.7 fixture")
    ocr_payload = json.dumps(
        {
            "pages": [
                {
                    "page_number": 1,
                    "raw_text": "Laptop\n15.000.000",
                    "lines": [
                        {"text": "Laptop", "confidence": 0.97},
                        {"text": "15.000.000", "confidence": 0.83},
                    ],
                }
            ]
        }
    )
    llm_item: dict[str, object] = {
        "item_name": "Laptop",
        "unit_price": 15_000_000,
        "currency": "VND",
        "page_number": 1,
        "source_text": "Laptop\n15.000.000",
        "confidence_score": 0.99,
        "field_confidence": {"item_name": 0.99, "unit_price": 0.99},
    }

    result = extract_documents(
        {"documents": [str(document)]},
        ocr_client=FakeOCRClient(ocr_payload),
        extraction_client=FakeExtractionClient([llm_item]),
    )

    draft_json = result["raw_extractions"][0]
    draft = ExtractionDraftPayload.model_validate(draft_json)
    assert str(draft.items[0].product_name.confidence) == "0.97"
    assert str(draft.items[0].unit_price.confidence) == "0.83"
