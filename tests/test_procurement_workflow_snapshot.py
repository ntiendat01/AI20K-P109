"""Regression coverage for analysis snapshot persistence."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from src.agents.nodes.normalize import normalize
from src.domain.procurement.workflow import ProcurementAnalysis
from src.domain.purchase_request import PRItem, PRMetadata, PRStatus, PurchaseRequest, UpdatePurchaseRequest
from src.domain.procurement.invalidation import InvalidationLevel, assess_purchase_request_impact
from src.domain.quotation.confirmation import Quotation, QuotationItem, QuotationStatus
from src.application.procurement.workflow import ProcurementWorkflow


def _purchase_request() -> PurchaseRequest:
    now = datetime.now(UTC)
    return PurchaseRequest(
        id="pr-analysis-snapshot",
        tenant_id="test",
        code="PR-500",
        creator_id="buyer-1",
        creator_name="Buyer",
        category="Thép xây dựng D16 CB400-V",
        requested_quantity=Decimal("20"),
        requested_uom="tấn",
        target_currency="VND",
        estimated_budget=Decimal("400000000.00"),
        delivery_due_date=date.today() + timedelta(days=10),
        items=[
            PRItem(
                order_index=0,
                product_name="Thép xây dựng D16 CB400-V",
                quantity=Decimal("20"),
                unit="tấn",
            )
        ],
        status=PRStatus.COMPARING,
        version=1,
        created_at=now,
        updated_at=now,
    )


def _quotation(index: int, unit_price: Decimal) -> Quotation:
    line_total = unit_price * Decimal("20")
    return Quotation(
        id=f"quote-{index}",
        pr_id="pr-analysis-snapshot",
        supplier_id=f"supplier-{index}",
        supplier_name=f"Nhà cung cấp {index}",
        source_filename=f"quote-{index}.pdf",
        source_hash=f"source-hash-{index}",
        source_path=f"/not-present/quote-{index}.pdf",
        source_content_type="application/pdf",
        currency="VND",
        status=QuotationStatus.CONFIRMED,
        items=[
            QuotationItem(
                product_name="Thép xây dựng D16 CB400-V",
                unit="tấn",
                quantity=20,
                unit_price=unit_price,
                line_total=line_total,
            )
        ],
        vat_rate=Decimal("0.10"),
        vat_included=True,
        shipping_fee=Decimal("0.00"),
        lead_time_days=5,
        warranty_months=12,
        goods_total_including_tax=line_total,
        shipping_total_including_tax=Decimal("0.00"),
    )


def test_descriptive_pr_metadata_updates_without_invalidating_analysis(tmp_path):
    workflow = ProcurementWorkflow(tmp_path / "workflow.sqlite", object(), tenant_id="test")
    original = _purchase_request().model_copy(
        update={"metadata": PRMetadata(department="Phòng Hành chính", requested_by="Nguyễn Minh Anh")}
    )
    changed = original.model_copy(
        update={"metadata": PRMetadata(department="Phòng IT", requested_by="Nguyễn Minh Anh", purpose="Bổ sung thiết bị")}
    )
    quotes = [_quotation(1, Decimal("15050000.00")), _quotation(2, Decimal("15180000.00"))]
    proposed = UpdatePurchaseRequest.model_validate(
        {key: value for key, value in changed.model_dump(mode="json").items() if key in UpdatePurchaseRequest.model_fields}
    )

    impact = assess_purchase_request_impact(original, proposed)

    assert impact.level == InvalidationLevel.METADATA
    assert {change.label for change in impact.changes} == {"Phòng ban", "Ghi chú / Mục đích"}
    assert workflow.revision(original, quotes) == workflow.revision(changed, quotes)


def _multi_line_quotation(index: int, prices: list[Decimal]) -> Quotation:
    items = [
        QuotationItem(
            product_name=f"Thiết bị {item_index}",
            unit="cái",
            quantity=2,
            unit_price=unit_price,
            line_total=unit_price * Decimal("2"),
        )
        for item_index, unit_price in enumerate(prices, start=1)
    ]
    line_subtotal = sum((item.line_total for item in items), Decimal("0"))
    factor = Decimal("1.10")
    shipping_fee = Decimal("100.00")
    return Quotation(
        id=f"multi-line-quote-{index}",
        pr_id="pr-analysis-snapshot",
        supplier_id=f"multi-line-supplier-{index}",
        supplier_name=f"Nhà cung cấp nhiều dòng {index}",
        source_filename=f"multi-line-{index}.pdf",
        source_hash=f"multi-line-source-hash-{index}",
        source_path=f"/not-present/multi-line-{index}.pdf",
        source_content_type="application/pdf",
        currency="VND",
        status=QuotationStatus.CONFIRMED,
        items=items,
        vat_rate=Decimal("0.10"),
        vat_included=False,
        shipping_fee=shipping_fee,
        lead_time_days=5,
        warranty_months=12,
        goods_total_including_tax=line_subtotal * factor,
        shipping_total_including_tax=shipping_fee * factor,
    )


def test_start_analysis_serializes_decimal_pr_quantity(tmp_path):
    """A Decimal PR quantity must not produce an HTTP-500-causing JSON error."""
    workflow = ProcurementWorkflow(tmp_path / "workflow.sqlite", object(), tenant_id="test")
    pr = _purchase_request()
    quotes = [_quotation(1, Decimal("15050000.00")), _quotation(2, Decimal("15180000.00"))]

    start = workflow.start_analysis(pr, quotes)

    assert start.should_execute
    assert start.run["status"] == "running"
    assert start.run["snapshot_revision"] == workflow.revision(pr, quotes)


def test_start_analysis_uses_all_confirmed_quote_lines(tmp_path):
    """Declared totals must be checked against every line, not only line one."""
    workflow = ProcurementWorkflow(tmp_path / "workflow.sqlite", object(), tenant_id="test")
    pr = _purchase_request()
    quotes = [
        _multi_line_quotation(1, [Decimal("100.00"), Decimal("250.00")]),
        _multi_line_quotation(2, [Decimal("120.00"), Decimal("240.00")]),
    ]

    start = workflow.start_analysis(pr, quotes)

    assert start.should_execute
    assert start.state is not None
    assert len(start.state["raw_extractions"]) == 4
    assert start.run["supplier_names"] == {quote.supplier_id: quote.supplier_name for quote in quotes}


def test_multi_line_bundle_keeps_buyer_confirmed_units_without_guessing(tmp_path):
    """Bundled quotes do not need a fictional conversion to the first line's UOM."""
    workflow = ProcurementWorkflow(tmp_path / "workflow.sqlite", object(), tenant_id="test")
    pr = _purchase_request()
    quotes = [
        _multi_line_quotation(1, [Decimal("100.00"), Decimal("250.00")]),
        _multi_line_quotation(2, [Decimal("120.00"), Decimal("240.00")]),
    ]
    quotes[0] = quotes[0].model_copy(
        update={
            "items": [
                quotes[0].items[0].model_copy(update={"unit": "bộ"}),
                quotes[0].items[1].model_copy(update={"unit": "gói"}),
            ]
        }
    )

    start = workflow.start_analysis(pr, quotes)

    assert start.should_execute
    assert start.state is not None
    assert start.state["pr_data"]["preserve_line_item_uom"] is True
    normalized = normalize(start.state)["normalized_quotes"]
    assert all(artifact.status == "normalized" for artifact in normalized)
    assert [item.normalized_uom for item in normalized[0].items] == ["bộ", "gói"]


def test_analysis_response_contract_accepts_current_pr_schema():
    """Loading a saved analysis must not fail FastAPI response validation."""
    pr = _purchase_request()

    response = ProcurementAnalysis.model_validate(
        {
            "pr_id": pr.id,
            "status": "needs_input",
            "pr": pr.model_dump(mode="json"),
        }
    )

    assert response.pr is not None
    assert response.pr.requested_quantity == Decimal("20")
