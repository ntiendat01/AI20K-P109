from __future__ import annotations

import logging
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from httpx import HTTPError

from src.agents.state import ProcurementAgentState
from src.models_v1.quotation.extraction import (
    ExtractedFieldValue,
    ExtractedItemField,
    ExtractionDraftPayload,
    FieldSource,
)
from src.services.quotation.ai_extraction import (
    ExtractionClient,
    OCRClient,
    PaddleOCRHostedClient,
)

logger = logging.getLogger(__name__)


def extract_documents(
    state: ProcurementAgentState,
    *,
    ocr_client: OCRClient | None = None,
    extraction_client: ExtractionClient | None = None,
) -> ProcurementAgentState:
    """Extract one models_v1 quotation draft for every local PDF in state."""
    documents = state.get("documents", [])
    if not documents:
        return {"raw_extractions": []}

    ocr = ocr_client or PaddleOCRHostedClient()
    extractor: ExtractionClient
    if extraction_client is None:
        from src.services.quotation.ai_extraction import ConfiguredExtraction

        extractor = ConfiguredExtraction()
    else:
        extractor = extraction_client

    drafts: list[dict[str, object]] = []
    logger.info("[NODE:extract_documents] Bắt đầu xử lý %d tài liệu", len(documents))

    for index, document in enumerate(documents, 1):
        logger.info(
            "[NODE:extract_documents] Xử lý tài liệu %d/%d: %s",
            index,
            len(documents),
            Path(document).name,
        )
        if not Path(document).is_file():
            logger.error("[NODE:extract_documents] Không tìm thấy tài liệu: %s", document)
            drafts.append(_empty_draft())
            continue

        try:
            ocr_text = ocr.extract_text(document)
            if not ocr_text.strip():
                logger.warning("[NODE:extract_documents] Tài liệu không có nội dung đọc được: %s", document)
                drafts.append(_empty_draft())
                continue

            raw_items = extractor.extract_items(ocr_text, document)
            drafts.append(_build_draft(document, raw_items))
        except (HTTPError, OSError, RuntimeError, TimeoutError, ValueError):
            logger.exception("[NODE:extract_documents] Lỗi xử lý document=%s", Path(document).name)
            drafts.append(_empty_draft())

    logger.info("[NODE:extract_documents] Hoàn tất Node: draft_count=%d", len(drafts))
    return {"raw_extractions": drafts}


def _build_draft(document: str, raw_items: list[dict[str, object]]) -> dict[str, object]:
    unique_items = _deduplicate(raw_items)
    draft = ExtractionDraftPayload(
        supplier_name=_header_field(document, unique_items, ("supplier_name", "supplier")),
        currency=_header_field(document, unique_items, ("currency",), uppercase=True),
        vat_rate=_header_field(document, unique_items, ("vat_rate",)),
        vat_included=_header_field(document, unique_items, ("vat_included", "is_vat_included")),
        lead_time_days=_header_field(document, unique_items, ("lead_time_days",)),
        warranty_months=_header_field(document, unique_items, ("warranty_months",)),
        payment_terms=_header_field(document, unique_items, ("payment_terms",)),
        items=[_build_item(document, item_index, item) for item_index, item in enumerate(unique_items)],
    )
    return draft.model_dump(mode="json")


def _build_item(document: str, index: int, item: Mapping[str, object]) -> ExtractedItemField:
    return ExtractedItemField(
        source_item_id=_stable_id(document, f"item-{index}"),
        product_name=_item_field(document, index, item, ("product_name", "item_name")),
        product_code=_optional_item_field(document, index, item, ("product_code",)),
        unit=_optional_item_field(document, index, item, ("unit", "uom")),
        quantity=_optional_item_field(document, index, item, ("quantity",)),
        unit_price=_item_field(document, index, item, ("unit_price",)),
    )


def _header_field(
    document: str,
    items: list[dict[str, object]],
    names: tuple[str, ...],
    *,
    uppercase: bool = False,
) -> ExtractedFieldValue | None:
    for index, item in enumerate(items):
        value = _first_value(item, names)
        if value is not None:
            text = _text_value(value)
            return _field_value(document, index, item, names, text.upper() if uppercase and text else text)
    return None


def _item_field(
    document: str,
    index: int,
    item: Mapping[str, object],
    names: tuple[str, ...],
) -> ExtractedFieldValue:
    return _field_value(document, index, item, names, _text_value(_first_value(item, names)))


def _optional_item_field(
    document: str,
    index: int,
    item: Mapping[str, object],
    names: tuple[str, ...],
) -> ExtractedFieldValue | None:
    value = _first_value(item, names)
    if value is None:
        return None
    return _field_value(document, index, item, names, _text_value(value))


def _field_value(
    document: str,
    index: int,
    item: Mapping[str, object],
    field_names: tuple[str, ...],
    value: str | None,
) -> ExtractedFieldValue:
    return ExtractedFieldValue(
        value=value,
        confidence=_field_confidence(item, field_names),
        source=_field_source(document, index, item, field_names[0]),
    )


def _field_source(
    document: str,
    index: int,
    item: Mapping[str, object],
    field_name: str,
) -> FieldSource | None:
    page_number = item.get("page_number")
    if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
        return None
    return FieldSource(
        document_id=_stable_id(document, "document"),
        page_number=page_number,
        block_id=f"p{page_number}-item-{index}-{field_name}",
    )


def _field_confidence(item: Mapping[str, object], field_names: tuple[str, ...]) -> Decimal:
    scores = item.get("field_confidence")
    score = _first_value(scores, field_names) if isinstance(scores, Mapping) else None
    if isinstance(score, bool) or not isinstance(score, (int, float, Decimal)):
        score = item.get("confidence_score", Decimal("0.50"))
    if isinstance(score, bool) or not isinstance(score, (int, float, Decimal)):
        score = Decimal("0.50")
    return max(Decimal(0), min(Decimal(1), Decimal(str(score))))


def _first_value(item: Mapping[str, object], names: tuple[str, ...]) -> object | None:
    for name in names:
        value = item.get(name)
        if value is not None:
            return value
    return None


def _text_value(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float, Decimal)):
        return format(Decimal(str(value)), "f")
    return str(value)


def _deduplicate(items: list[dict[str, object]]) -> list[dict[str, object]]:
    unique: list[dict[str, object]] = []
    seen: set[tuple[str | None, ...]] = set()
    for item in items:
        key = tuple(
            _text_value(item.get(field))
            for field in ("item_name", "product_name", "unit_price", "quantity", "unit", "uom")
        )
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _stable_id(document: str, suffix: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{Path(document).resolve()}#{suffix}"))


def _empty_draft() -> dict[str, object]:
    return ExtractionDraftPayload().model_dump(mode="json")
