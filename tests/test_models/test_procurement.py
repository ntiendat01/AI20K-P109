from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.procurement import (
    NormalizedLine,
    PRData,
    RawExtraction,
    SourceReference,
    TCOResult,
)


def test_quote_line_migrates_current_extraction_aliases() -> None:
    line = RawExtraction.model_validate(
        {
            "extraction_id": "doc-1:0",
            "document": "quote-a.pdf",
            "page_number": 2,
            "supplier": "NCC A",
            "item_name": "Vật tư A",
            "unit_price": 100_000,
            "quantity": 2,
            "unit": "cái",
            "currency": "VND",
            "vat_rate": 0.1,
            "is_vat_included": False,
            "shipping_fee": 25_000,
        }
    )

    assert line.supplier_id == "NCC A"
    assert line.source.document_path == "quote-a.pdf"
    assert line.source.page_number == 2
    assert line.vat_included is False
    assert line.surcharges[0].kind == "shipping"
    assert line.surcharges[0].amount == 25_000


def test_normalized_line_preserves_commercial_and_source_fields() -> None:
    line = NormalizedLine.model_validate(
        {
            "extraction_id": "doc-1:0",
            "source": {"document_id": "doc-1", "page_number": 1},
            "supplier_id": "NCC A",
            "item_name": "Vật tư A",
            "unit_price": 100,
            "quantity": 10,
            "unit": "hộp",
            "currency": "USD",
            "vat_rate": 0.1,
            "vat_included": False,
            "warranty_months": 12,
            "lead_time_days": 7,
            "normalized_price": 254_000,
            "normalized_quantity": 100,
            "normalized_uom": "cái",
            "normalized_currency": "VND",
        }
    )

    assert line.normalized_unit_price == 254_000
    assert line.currency == "USD"
    assert line.vat_rate == 0.1
    assert line.warranty_months == 12
    assert line.lead_time_days == 7
    assert line.source.document_id == "doc-1"


def test_pr_data_serializes_with_canonical_names() -> None:
    pr_data = PRData.model_validate(
        {
            "pr_code": "PR-001",
            "quantity": 10,
            "deadline": "2026-12-31",
        }
    )

    assert pr_data.model_dump(mode="json")["pr_number"] == "PR-001"
    assert pr_data.target_currency == "VND"


def test_contract_rejects_invalid_vat_rate() -> None:
    with pytest.raises(ValidationError):
        RawExtraction.model_validate(
            {
                "extraction_id": "doc-1:0",
                "source": {"document_id": "doc-1"},
                "vat_rate": 10,
            }
        )


def test_quote_line_keeps_missing_currency_unknown() -> None:
    line = RawExtraction.model_validate(
        {
            "extraction_id": "doc-1:0",
            "source": {"document_id": "doc-1"},
        }
    )

    assert line.currency is None


def test_source_reference_requires_a_location() -> None:
    with pytest.raises(ValidationError):
        SourceReference()


def test_field_confidence_rejects_scores_outside_unit_interval() -> None:
    with pytest.raises(ValidationError):
        RawExtraction.model_validate(
            {
                "extraction_id": "doc-1:0",
                "source": {"document_id": "doc-1"},
                "field_confidence": {"unit_price": 1.1},
            }
        )


def test_lead_time_range_rejects_reversed_bounds() -> None:
    with pytest.raises(ValidationError):
        RawExtraction.model_validate(
            {
                "extraction_id": "doc-1:0",
                "source": {"document_id": "doc-1"},
                "lead_time_min": 10,
                "lead_time_max": 2,
            }
        )


def test_calculated_tco_requires_a_total() -> None:
    with pytest.raises(ValidationError):
        TCOResult(supplier_id="NCC A", status="calculated", total_tco=None)
