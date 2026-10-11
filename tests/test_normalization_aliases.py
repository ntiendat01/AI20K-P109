from src.agents.nodes.normalize import normalize
from src.models_v1.analysis.normalization import NormalizationStatus
from src.models_v1.quotation.confirmation import (
    ConfirmedItemPayload,
    QuotationConfirmationRequest,
)


def test_metric_ton_alias_normalizes_to_vietnamese_ton() -> None:
    quote = QuotationConfirmationRequest(
        supplier_name="NCC thép",
        currency="VND",
        vat_rate="0.10",
        vat_included=False,
        lead_time_days=7,
        warranty_months=12,
        payment_terms="Thanh toán sau nghiệm thu",
        items=[
            ConfirmedItemPayload(
                product_name="Thép thanh vằn D16",
                unit="MT",
                quantity="20",
                unit_price="15180000.00",
            )
        ],
    )

    result = normalize(
        {
            "case_id": "pr-steel",
            "confirmed_quotes": [quote],
            "pr_data": {"target_uom": "tấn", "target_currency": "VND"},
        }
    )

    artifact = result["normalized_quotes"][0]
    assert artifact.status == NormalizationStatus.NORMALIZED
    assert artifact.items[0].normalized_quantity == 20
    assert artifact.items[0].normalized_uom == "tấn"
