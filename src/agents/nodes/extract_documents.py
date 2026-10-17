from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from httpx import HTTPError

from src.agents.state import ProcurementAgentState
from src.domain.agent.quotation.extraction import (
    ExtractedFieldValue,
    ExtractedItemField,
    ExtractionDraftPayload,
    FieldSource,
)
from src.infrastructure.documents.pdf_extractor import PDFTextExtractor
from src.infrastructure.ocr.client import OCRClient
from src.infrastructure.quotation.ai_extraction import ExtractionClient

logger = logging.getLogger(__name__)


def extract_documents(
    state: ProcurementAgentState,
    *,
    ocr_client: OCRClient | None = None,
    extraction_client: ExtractionClient | None = None,
) -> ProcurementAgentState:
    """Extract one strict agent-contract quotation draft for every local PDF in state."""
    documents = state.get("documents", [])
    if not documents:
        return {"raw_extractions": []}

    ocr = ocr_client or PDFTextExtractor()
    extractor: ExtractionClient
    if extraction_client is None:
        from src.infrastructure.quotation.ai_extraction import ConfiguredExtraction

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
            ocr_lines = _extract_lines_from_ocr(ocr_text)
            drafts.append(_build_draft(document, raw_items, ocr_lines=ocr_lines))
        except (HTTPError, OSError, RuntimeError, TimeoutError, ValueError):
            logger.exception("[NODE:extract_documents] Lỗi xử lý document=%s", Path(document).name)
            drafts.append(_empty_draft())

    logger.info("[NODE:extract_documents] Hoàn tất Node: draft_count=%d", len(drafts))
    return {"raw_extractions": drafts}


def _build_draft(
    document: str,
    raw_items: list[dict[str, object]],
    ocr_lines: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    unique_items = _deduplicate(raw_items)
    draft = ExtractionDraftPayload(
        supplier_name=_header_field(document, unique_items, ("supplier_name", "supplier"), ocr_lines=ocr_lines),
        currency=_header_field(document, unique_items, ("currency",), uppercase=True, ocr_lines=ocr_lines),
        vat_rate=_header_field(document, unique_items, ("vat_rate",), ocr_lines=ocr_lines),
        vat_included=_header_field(document, unique_items, ("vat_included", "is_vat_included"), ocr_lines=ocr_lines),
        lead_time_days=_header_field(
            document, unique_items, ("lead_time_days", "delivery_time", "lead_time"), ocr_lines=ocr_lines
        ),
        warranty_months=_header_field(document, unique_items, ("warranty_months",), ocr_lines=ocr_lines),
        payment_terms=_header_field(document, unique_items, ("payment_terms",), ocr_lines=ocr_lines),
        items=[
            _build_item(document, item_index, item, ocr_lines=ocr_lines) for item_index, item in enumerate(unique_items)
        ],
    )
    return draft.model_dump(mode="json")


def _build_item(
    document: str,
    index: int,
    item: Mapping[str, object],
    ocr_lines: list[dict[str, object]] | None = None,
) -> ExtractedItemField:
    return ExtractedItemField(
        source_item_id=_stable_id(document, f"item-{index}"),
        product_name=_item_field(document, index, item, ("product_name", "item_name"), ocr_lines=ocr_lines),
        product_code=_optional_item_field(document, index, item, ("product_code",), ocr_lines=ocr_lines),
        unit=_optional_item_field(document, index, item, ("unit", "uom"), ocr_lines=ocr_lines),
        quantity=_optional_item_field(document, index, item, ("quantity",), ocr_lines=ocr_lines),
        unit_price=_item_field(document, index, item, ("unit_price",), ocr_lines=ocr_lines),
    )


def _header_field(
    document: str,
    items: list[dict[str, object]],
    names: tuple[str, ...],
    *,
    uppercase: bool = False,
    ocr_lines: list[dict[str, object]] | None = None,
) -> ExtractedFieldValue | None:
    for index, item in enumerate(items):
        value = _first_value(item, names)
        if value is not None:
            text = _text_value(value)
            return _field_value(
                document, index, item, names, text.upper() if uppercase and text else text, ocr_lines=ocr_lines
            )
    return None


def _item_field(
    document: str,
    index: int,
    item: Mapping[str, object],
    names: tuple[str, ...],
    ocr_lines: list[dict[str, object]] | None = None,
) -> ExtractedFieldValue:
    return _field_value(document, index, item, names, _text_value(_first_value(item, names)), ocr_lines=ocr_lines)


def _optional_item_field(
    document: str,
    index: int,
    item: Mapping[str, object],
    names: tuple[str, ...],
    ocr_lines: list[dict[str, object]] | None = None,
) -> ExtractedFieldValue | None:
    value = _first_value(item, names)
    if value is None:
        return None
    return _field_value(document, index, item, names, _text_value(value), ocr_lines=ocr_lines)


def _field_value(
    document: str,
    index: int,
    item: Mapping[str, object],
    field_names: tuple[str, ...],
    value: str | None,
    ocr_lines: list[dict[str, object]] | None = None,
) -> ExtractedFieldValue:
    raw_val = _first_value(item, field_names)
    matched_conf = _match_ocr_line_confidence(raw_val, ocr_lines or [])
    confidence = matched_conf if matched_conf is not None else _field_confidence(item, field_names)
    return ExtractedFieldValue(
        value=value,
        confidence=confidence,
        source=_field_source(document, index, item, field_names[0]),
    )


def _extract_lines_from_ocr(ocr_text: str) -> list[dict[str, object]]:
    try:
        data = json.loads(ocr_text)
        if isinstance(data, dict):
            pages = data.get("pages", [])
            lines: list[dict[str, object]] = []
            if isinstance(pages, list):
                for page in pages:
                    if isinstance(page, dict):
                        for line in page.get("lines", []):
                            if isinstance(line, dict):
                                lines.append(line)
            return lines
    except Exception:
        pass
    return []


def _match_ocr_line_confidence(
    value: object | None,
    ocr_lines: list[dict[str, object]],
) -> Decimal | None:
    if value is None or not ocr_lines:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    val_digits = re.sub(r"[^\d]", "", val_str)

    # 1. Exact or case-insensitive match on text
    for line in ocr_lines:
        line_text = str(line.get("text", "")).strip()
        if not line_text:
            continue
        conf = line.get("confidence")
        if not isinstance(conf, (int, float, Decimal)):
            continue
        if val_str.lower() == line_text.lower():
            return Decimal(str(conf))

    # 2. Number match (e.g. 15000000 matches 15.000.000)
    if val_digits and len(val_digits) >= 2:
        for line in ocr_lines:
            line_text = str(line.get("text", "")).strip()
            line_digits = re.sub(r"[^\d]", "", line_text)
            if val_digits == line_digits:
                conf = line.get("confidence")
                if isinstance(conf, (int, float, Decimal)):
                    return Decimal(str(conf))

    # 3. Substring match
    for line in ocr_lines:
        line_text = str(line.get("text", "")).strip()
        if not line_text:
            continue
        conf = line.get("confidence")
        if not isinstance(conf, (int, float, Decimal)):
            continue
        if len(val_str) >= 3 and (val_str.lower() in line_text.lower() or line_text.lower() in val_str.lower()):
            return Decimal(str(conf))

    return None


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


def _field_confidence(item: Mapping[str, object], field_names: tuple[str, ...]) -> Decimal | None:
    scores = item.get("field_confidence")
    score = _first_value(scores, field_names) if isinstance(scores, Mapping) else None
    if isinstance(score, bool) or not isinstance(score, (int, float, Decimal)):
        score = item.get("confidence_score")
    if isinstance(score, bool) or not isinstance(score, (int, float, Decimal)):
        return None
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
        cleaned = re.sub(r"\s*\[ocr_conf:\s*[\d.]+\]", "", value).strip()
        return cleaned or None
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
