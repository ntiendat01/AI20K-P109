from __future__ import annotations

from decimal import Decimal
from typing import Final

from pydantic import ValidationError

from src.agents.state import ProcurementAgentState
from src.domain.agent.quotation.extraction import (
    ExtractedFieldValue,
    ExtractionDraftPayload,
    ValidatedExtraction,
    ValidationIssue,
    ValidationSeverity,
)
from src.infrastructure.repositories.system_settings import get_dynamic_settings

DEFAULT_CONFIDENCE_THRESHOLD: Final = Decimal("0.80")


def validate_extraction(
    state: ProcurementAgentState,
    confidence_threshold: Decimal | None = None,
) -> ProcurementAgentState:
    """Validate agent-contract extraction drafts before mandatory Buyer review."""
    threshold = (
        confidence_threshold
        if confidence_threshold is not None
        else Decimal(str(get_dynamic_settings().confidence_threshold))
    )
    validations: list[ValidatedExtraction] = []
    for raw_draft in state.get("raw_extractions", []):
        try:
            draft = ExtractionDraftPayload.model_validate(raw_draft)
        except ValidationError as error:
            validations.append(_schema_failure(error))
            continue
        validations.append(_validate_draft(draft, threshold))
    return {"validated_extractions": validations, "review_mode": "mandatory"}


def _validate_draft(draft: ExtractionDraftPayload, threshold: Decimal) -> ValidatedExtraction:
    issues = [
        *_required_field_issues("supplier_name", draft.supplier_name, threshold),
        *_required_field_issues("currency", draft.currency, threshold),
        *_optional_field_issues("vat_rate", draft.vat_rate, threshold),
        *_optional_field_issues("vat_included", draft.vat_included, threshold),
        *_optional_field_issues("lead_time_days", draft.lead_time_days, threshold),
        *_optional_field_issues("warranty_months", draft.warranty_months, threshold),
        *_optional_field_issues("payment_terms", draft.payment_terms, threshold),
    ]
    if not draft.items:
        issues.append(_blocking_issue("items", "MISSING_ITEMS"))
    for index, item in enumerate(draft.items):
        prefix = f"items[{index}]"
        issues.extend(_required_field_issues(f"{prefix}.product_name", item.product_name, threshold))
        issues.extend(_optional_field_issues(f"{prefix}.product_code", item.product_code, threshold))
        issues.extend(_required_field_issues(f"{prefix}.unit", item.unit, threshold))
        issues.extend(_required_field_issues(f"{prefix}.quantity", item.quantity, threshold))
        issues.extend(_required_field_issues(f"{prefix}.unit_price", item.unit_price, threshold))
    schema_valid = all(issue.severity is not ValidationSeverity.BLOCKING for issue in issues)
    return ValidatedExtraction(schema_valid=schema_valid, issues=issues)


def _required_field_issues(
    path: str,
    field: ExtractedFieldValue | None,
    threshold: Decimal,
) -> list[ValidationIssue]:
    if field is None or field.value is None or not field.value.strip():
        return [_blocking_issue(path, "MISSING_REQUIRED_FIELD")]
    return _field_issues(path, field, threshold)


def _optional_field_issues(
    path: str,
    field: ExtractedFieldValue | None,
    threshold: Decimal,
) -> list[ValidationIssue]:
    return [] if field is None else _field_issues(path, field, threshold)


def _field_issues(path: str, field: ExtractedFieldValue, threshold: Decimal) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if field.confidence is not None and field.confidence < threshold:
        issues.append(
            ValidationIssue(
                field_path=path,
                code="LOW_CONFIDENCE",
                severity=ValidationSeverity.WARNING,
                confidence=field.confidence,
            )
        )
    if field.source is None:
        issues.append(
            ValidationIssue(
                field_path=path,
                code="MISSING_PROVENANCE",
                severity=ValidationSeverity.WARNING,
                confidence=field.confidence,
            )
        )
    return issues


def _blocking_issue(path: str, code: str) -> ValidationIssue:
    return ValidationIssue(field_path=path, code=code, severity=ValidationSeverity.BLOCKING)


def _schema_failure(error: ValidationError) -> ValidatedExtraction:
    issues = [_blocking_issue(".".join(str(part) for part in item["loc"]), "SCHEMA_INVALID") for item in error.errors()]
    return ValidatedExtraction(schema_valid=False, issues=issues)
