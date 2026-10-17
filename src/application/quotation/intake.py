"""Recoverable document intake; only explicit Buyer confirmation resumes HITL-1."""

import json
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.agents.nodes.extract_documents import extract_documents
from src.agents.nodes.human_review_extraction import human_review_extraction
from src.agents.nodes.validate_extraction import validate_extraction
from src.agents.state import ProcurementAgentState
from src.application.quotation.parser import ExtractedQuotation
from src.core.config import get_settings
from src.domain.agent.quotation.extraction import ExtractedFieldValue, ExtractedItemField, ExtractionDraftPayload
from src.domain.procurement.contracts import QuotationConfirmation
from src.domain.quotation.confirmation import Quotation, QuotationItem
from src.infrastructure.documents.pdf_extractor import PDFTextExtractor
from src.infrastructure.llm import get_llm
from src.infrastructure.quotation.ai_extraction import (
    _strip_json_fence,
)
from src.infrastructure.repositories.system_settings import get_dynamic_settings

logger = logging.getLogger(__name__)


class ConfiguredExtraction:
    def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, object]]:
        settings = get_settings()
        response = get_llm().invoke(
            [
                {"role": "system", "content": settings.extraction_prompt},
                {
                    "role": "user",
                    "content": json.dumps({"document": document_path, "ocr_result": ocr_text}, ensure_ascii=False),
                },
            ]
        )
        response_metadata = getattr(response, "response_metadata", {}) or {}
        usage = response_metadata.get("token_usage", {}) or {} if isinstance(response_metadata, dict) else {}
        if not usage and hasattr(response, "usage_metadata") and isinstance(response.usage_metadata, dict):
            usage = {
                "prompt_tokens": response.usage_metadata.get("input_tokens"),
                "completion_tokens": response.usage_metadata.get("output_tokens"),
                "total_tokens": response.usage_metadata.get("total_tokens"),
            }
        prompt_tokens = usage.get("prompt_tokens") or "N/A"
        completion_tokens = usage.get("completion_tokens") or "N/A"
        total_tokens = usage.get("total_tokens") or "N/A"
        logger.info(
            "Intake extraction token usage: input_tokens=%s output_tokens=%s total_tokens=%s",
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )

        raw_content = getattr(response, "content", "")
        logger.debug(
            "Intake extraction response received: document=%s content_type=%s content_length=%s",
            Path(document_path).name,
            type(raw_content).__name__,
            len(raw_content) if isinstance(raw_content, (str, list, dict)) else None,
        )

        payload = json.loads(_strip_json_fence(raw_content))
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("Extraction response must contain items")
        logger.info(
            "Intake extraction completed: document=%s item_count=%d",
            Path(document_path).name,
            len(items),
        )
        return items


def intake_graph(*, ocr=None, extractor=None, review_only=False):
    graph = StateGraph(ProcurementAgentState)
    graph.add_node(
        "extract_documents",
        lambda state: extract_documents(
            state, ocr_client=ocr or PDFTextExtractor(), extraction_client=extractor or ConfiguredExtraction()
        ),
    )
    graph.add_node("validate_extraction", validate_extraction)
    graph.add_node(
        "human_review_extraction",
        lambda state: human_review_extraction(
            {**state, "review_mode": "mandatory", "require_explicit_confirmation": True}
        ),
    )
    graph.set_entry_point("human_review_extraction" if review_only else "extract_documents")
    graph.add_edge("extract_documents", "validate_extraction")
    graph.add_edge("validate_extraction", "human_review_extraction")
    graph.add_edge("human_review_extraction", END)
    return graph.compile(checkpointer=MemorySaver())


def extract_for_quotation(
    quotation: Quotation, *, ocr=None, extractor=None
) -> tuple[ExtractedQuotation, list[dict], str]:
    class RecordingOCR:
        text = ""

        def extract_text(self, path: str) -> str:
            self.text = (ocr or PDFTextExtractor()).extract_text(path)
            return self.text

    recorded = RecordingOCR()
    graph = intake_graph(ocr=recorded, extractor=extractor)
    result = graph.invoke(
        {"case_id": quotation.pr_id, "documents": [quotation.source_path]},
        {"configurable": {"thread_id": quotation.id}},
    )
    extracted, raw = _project_v1_draft(quotation, result.get("raw_extractions", []))
    warnings = [
        "Dữ liệu AI chưa được xác nhận. Đối chiếu các trường và tổng tiền trước khi tiếp tục.",
        *extracted.warnings,
    ]
    if not extracted.items:
        warnings.append("AI chưa trích xuất được dòng hàng. Hãy kiểm tra lại bảng trong file gốc hoặc trích xuất lại.")
    if any(line.get("extraction_error") for line in raw):
        warnings.append("AI chưa đọc được đầy đủ nội dung. Hãy kiểm tra provider hoặc nhập lại từ file gốc.")
    extracted.warnings = warnings
    logger.info(
        "Quotation intake completed: quotation_id=%s item_count=%d warning_count=%d",
        quotation.id,
        len(extracted.items),
        len(extracted.warnings),
    )
    return extracted, raw, recorded.text


def _project_v1_draft(quotation: Quotation, raw_drafts: list[object]) -> tuple[ExtractedQuotation, list[dict]]:
    """Project the agent evidence-rich draft into the legacy quotation review shape.

    The upload/review API persists flat quotation rows until its public contract
    is replaced.  ``extract_documents`` now correctly emits one
    ``ExtractionDraftPayload`` per PDF, so this adapter unwraps only the
    values that legacy UI fields require and retains agent provenance in the
    persisted agent rows. It is deliberately the sole agent-to-legacy boundary.
    """
    draft = ExtractionDraftPayload.model_validate(raw_drafts[0]) if raw_drafts else ExtractionDraftPayload()
    currency = _field_text(draft.currency) or ""
    supplier_name = _field_text(draft.supplier_name) or quotation.supplier_name
    lines = [_legacy_agent_line(draft, item, currency) for item in draft.items]
    review_lines: list[dict] = []
    review_items: list[QuotationItem] = []
    warnings: list[str] = []
    for line in lines:
        review_item, reason = _review_item(line)
        if review_item is None:
            warnings.append(f"Dòng {line['extraction_id']} chưa thể đưa vào biểu mẫu xác nhận: {reason}.")
            continue
        review_lines.append(line)
        review_items.append(review_item)
    return (
        ExtractedQuotation(
            supplier_name=supplier_name,
            currency=currency,
            items=review_items,
            delivery_time=_display_duration(_field_text(draft.lead_time_days)),
            payment_terms=_field_text(draft.payment_terms) or "",
            warranty=_display_months(_field_text(draft.warranty_months)),
            warnings=warnings,
        ),
        review_lines,
    )


def _legacy_agent_line(draft: ExtractionDraftPayload, item: ExtractedItemField, currency: str) -> dict:
    fields = {
        "supplier": draft.supplier_name,
        "item_name": item.product_name,
        "unit": item.unit,
        "quantity": item.quantity,
        "unit_price": item.unit_price,
        "currency": draft.currency,
        "vat_rate": draft.vat_rate,
        "vat_included": draft.vat_included,
        "lead_time_days": draft.lead_time_days,
        "warranty_months": draft.warranty_months,
        "payment_terms": draft.payment_terms,
    }
    confidences = {
        name: float(field.confidence)
        for name, field in fields.items()
        if field is not None and field.confidence is not None
    }
    source = next((field.source for field in fields.values() if field is not None and field.source is not None), None)
    return {
        "extraction_id": item.source_item_id,
        "source": source.model_dump(mode="json") if source is not None else {},
        "supplier_id": _field_text(draft.supplier_name),
        "item_name": _field_text(item.product_name),
        "unit_price": _as_float(_field_text(item.unit_price)),
        "quantity": _as_float(_field_text(item.quantity)),
        "unit": _field_text(item.unit) or "",
        "currency": currency,
        "vat_rate": _as_float(_field_text(draft.vat_rate)),
        "vat_included": _as_bool(_field_text(draft.vat_included)),
        "surcharges": [],
        "warranty_months": _as_int(_field_text(draft.warranty_months)),
        "lead_time_days": _as_int(_field_text(draft.lead_time_days)),
        "payment_terms": _field_text(draft.payment_terms) or "",
        "confidence_score": min(confidences.values(), default=1.0) if confidences else 1.0,
        "field_confidence": confidences,
        "field_needs_confirmation": {
            name: (
                field.confidence is not None
                and float(field.confidence) < get_dynamic_settings().confidence_threshold
            )
            for name, field in fields.items()
            if field is not None
        },
        "needs_confirmation": any(
            field.confidence is not None
            and float(field.confidence) < get_dynamic_settings().confidence_threshold
            for field in fields.values()
            if field is not None
        ),
        "confirmed_by_human": False,
        "extraction_error": None,
    }


def _review_item(line: dict) -> tuple[QuotationItem | None, str]:
    try:
        quantity = Decimal(str(line["quantity"]))
        price = Decimal(str(line["unit_price"]))
        if quantity <= 0:
            return None, "số lượng phải lớn hơn 0"
        if quantity != quantity.to_integral_value():
            return None, "số lượng lẻ chưa được schema báo giá cũ hỗ trợ"
        if price <= 0:
            return None, "đơn giá phải lớn hơn 0"
        if price.as_tuple().exponent < -2:
            return None, "đơn giá có quá 2 chữ số thập phân"
        return QuotationItem(
            product_name=str(line.get("item_name") or "").strip(),
            unit=str(line.get("unit") or "").strip(),
            quantity=int(quantity),
            unit_price=price,
            line_total=price * quantity,
        ), ""
    except (InvalidOperation, TypeError, ValueError):
        return None, "thiếu hoặc không đọc được số lượng/đơn giá"


def _field_text(field: ExtractedFieldValue | None) -> str | None:
    return field.value.strip() if field is not None and field.value is not None and field.value.strip() else None


def _as_float(value: str | None) -> float | None:
    try:
        return float(Decimal(value)) if value is not None else None
    except (InvalidOperation, ValueError):
        return None


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    cleaned = value.strip()
    try:
        number = Decimal(cleaned)
        return int(number) if number == number.to_integral_value() else None
    except (InvalidOperation, ValueError):
        pass

    # Extract numbers from natural language strings like "2-4 ngày", "7 ngày", "1-2 tuần"
    import re

    numbers = [int(n) for n in re.findall(r"\d+", cleaned)]
    if not numbers:
        return None

    max_num = max(numbers)
    lower = cleaned.lower()
    if "tuần" in lower or "week" in lower:
        return max_num * 7
    if "tháng" in lower or "month" in lower:
        return max_num * 30

    return max_num


def _as_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    return (
        True
        if normalized in {"true", "1", "yes", "có"}
        else False
        if normalized in {"false", "0", "no", "không"}
        else None
    )


def _display_duration(value: str | None) -> str:
    if not value or not value.strip():
        return ""
    cleaned = value.strip()
    if any(c.isalpha() for c in cleaned):
        return cleaned
    days = _as_int(cleaned)
    return f"{days} ngày lịch" if days is not None else cleaned


def _display_months(value: str | None) -> str:
    months = _as_int(value)
    return f"{months} tháng" if months is not None else ""


def resume_confirmation(quotation: Quotation, payload: QuotationConfirmation) -> list[dict]:
    if len(payload.items) != len(quotation.agent_extractions):
        raise ValueError("Số dòng xác nhận cần khớp dữ liệu extraction; trích xuất lại nếu cần đổi cấu trúc.")
    confirmed_lines = []
    for raw, item in zip(quotation.agent_extractions, payload.items, strict=True):
        confirmed_lines.append(
            {
                **raw,
                "supplier_id": payload.supplier_name,
                "item_name": item.product_name,
                "quantity": float(item.quantity),
                "unit_price": float(item.unit_price),
                "unit": item.unit,
                "currency": payload.currency,
                "vat_included": payload.vat_included,
                "vat_rate": float(payload.vat_rate) if payload.vat_rate is not None else None,
                "lead_time_days": payload.lead_time_days,
                "warranty_months": payload.warranty_months,
                "surcharges": [
                    {
                        "kind": "shipping",
                        "description": "Buyer confirmed shipping",
                        "amount": float(payload.shipping_fee),
                        "currency": payload.currency,
                    }
                ]
                if payload.shipping_fee is not None
                else [],
                "extraction_error": None,
                "needs_confirmation": False,
                "confirmed_by_human": True,
            }
        )
    return confirmed_lines
