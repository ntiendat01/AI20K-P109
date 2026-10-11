from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.models_v1.quotation.extraction import (
    ExtractedFieldValue,
    ExtractedItemField,
    ExtractionDraftPayload,
    FieldSource,
)


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing API endpoints (lazy-loaded)."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests."""
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock


@pytest.fixture
def sample_field_source() -> FieldSource:
    """Fixture providing a standard FieldSource for models_v1 tests."""
    return FieldSource(document_id="doc-1", page_number=1, block_id="blk-1")


@pytest.fixture
def make_extracted_field():
    """Factory fixture for creating ExtractedFieldValue with defaults."""

    def _factory(
        value: str | None = "Sample Value",
        confidence: str | Decimal = "0.95",
        source: FieldSource | None = None,
        *,
        has_source: bool = True,
    ) -> ExtractedFieldValue:
        if source is None and has_source:
            source = FieldSource(document_id="doc-1", page_number=1, block_id=f"blk-{value or 'none'}")
        return ExtractedFieldValue(
            value=value,
            confidence=Decimal(str(confidence)),
            source=source,
        )

    return _factory


@pytest.fixture
def sample_valid_draft_payload(make_extracted_field) -> ExtractionDraftPayload:
    """Fixture providing a valid models_v1 ExtractionDraftPayload."""
    return ExtractionDraftPayload(
        supplier_name=make_extracted_field("Công ty ABC", "0.95"),
        currency=make_extracted_field("VND", "0.99"),
        vat_rate=make_extracted_field("0.10", "0.90"),
        vat_included=make_extracted_field("true", "0.90"),
        lead_time_days=make_extracted_field("7", "0.85"),
        warranty_months=make_extracted_field("12", "0.88"),
        payment_terms=make_extracted_field("30 ngày", "0.90"),
        items=[
            ExtractedItemField(
                source_item_id="item-1",
                product_name=make_extracted_field("Laptop Dell", "0.92"),
                product_code=make_extracted_field("DELL-5520", "0.90"),
                unit=make_extracted_field("cái", "0.90"),
                quantity=make_extracted_field("2", "0.95"),
                unit_price=make_extracted_field("20000000.00", "0.91"),
            )
        ],
    )


@pytest.fixture
def sample_raw_draft_dict(sample_valid_draft_payload) -> dict:
    """Fixture returning raw dict form of a valid draft payload for state injection."""
    return sample_valid_draft_payload.model_dump(mode="json")


@pytest.fixture
def integration(tmp_path):
    from src.api.routes.procurement_workflow import get_procurement_workflow
    from src.main import app
    from src.services.procurement.purchase_orders import PurchaseOrderRepository, get_po_repository
    from src.services.procurement.purchase_requests import PurchaseRequestRepository, get_pr_repository
    from src.services.quotation.repository import QuotationRepository, get_quotation_repository
    from tests.fixtures.procurement_integration import integration_service

    service = integration_service(tmp_path)
    prs = PurchaseRequestRepository(tmp_path / "prs.json")
    quotes = QuotationRepository(tmp_path / "quotes.json", tmp_path / "uploads")
    pos = PurchaseOrderRepository(tmp_path / "pos.json")
    app.dependency_overrides.update(
        {
            get_pr_repository: lambda: prs,
            get_quotation_repository: lambda: quotes,
            get_po_repository: lambda: pos,
            get_procurement_workflow: lambda: service,
        }
    )
    yield service, prs, quotes, pos, service.decision_model
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def disable_live_provider_configuration(monkeypatch):
    """Never use a developer's credentials/endpoints while running the test suite."""
    from src.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "auto")
    for field in (
        "openai_api_key",
        "openrouter_api_key",
        "groq_api_key",
        "gemini_api_key",
        "qwen_api_key",
        "qwen_base_url",
        "paddleocr_access_token",
    ):
        monkeypatch.setattr(settings, field, "")
    monkeypatch.setattr(settings, "paddleocr_base_url", None)
