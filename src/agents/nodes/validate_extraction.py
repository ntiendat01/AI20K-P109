from __future__ import annotations

from decimal import Decimal
from typing import Final

from pydantic import ValidationError

from src.agents.state import ProcurementAgentState
from src.models_v1.quotation.extraction import (
    ExtractedFieldValue,
    ExtractionDraftPayload,
    ValidatedExtraction,
    ValidationIssue,
    ValidationSeverity,
)

CONFIDENCE_THRESHOLD: Final = Decimal("0.80")


def validate_extraction(state: ProcurementAgentState) -> ProcurementAgentState:
    """Validate models_v1 extraction drafts before mandatory Buyer review."""
    validations: list[ValidatedExtraction] = []
    for raw_draft in state.get("raw_extractions", []):
        try:
            draft = ExtractionDraftPayload.model_validate(raw_draft)
        except ValidationError as error:
            validations.append(_schema_failure(error))
            continue
        validations.append(_validate_draft(draft))
    return {"validated_extractions": validations, "review_mode": "mandatory"}


def _validate_draft(draft: ExtractionDraftPayload) -> ValidatedExtraction:
    issues = [
        *_required_field_issues("supplier_name", draft.supplier_name),
        *_required_field_issues("currency", draft.currency),
        *_optional_field_issues("vat_rate", draft.vat_rate),
        *_optional_field_issues("vat_included", draft.vat_included),
        *_optional_field_issues("lead_time_days", draft.lead_time_days),
        *_optional_field_issues("warranty_months", draft.warranty_months),
        *_optional_field_issues("payment_terms", draft.payment_terms),
    ]
    if not draft.items:
        issues.append(_blocking_issue("items", "MISSING_ITEMS"))
    for index, item in enumerate(draft.items):
        prefix = f"items[{index}]"
        issues.extend(_required_field_issues(f"{prefix}.product_name", item.product_name))
        issues.extend(_optional_field_issues(f"{prefix}.product_code", item.product_code))
        issues.extend(_required_field_issues(f"{prefix}.unit", item.unit))
        issues.extend(_required_field_issues(f"{prefix}.quantity", item.quantity))
        issues.extend(_required_field_issues(f"{prefix}.unit_price", item.unit_price))
    schema_valid = all(issue.severity is not ValidationSeverity.BLOCKING for issue in issues)
    return ValidatedExtraction(schema_valid=schema_valid, issues=issues)


def _required_field_issues(path: str, field: ExtractedFieldValue | None) -> list[ValidationIssue]:
    if field is None or field.value is None or not field.value.strip():
        return [_blocking_issue(path, "MISSING_REQUIRED_FIELD")]
    return _field_issues(path, field)


def _optional_field_issues(path: str, field: ExtractedFieldValue | None) -> list[ValidationIssue]:
    return [] if field is None else _field_issues(path, field)


def _field_issues(path: str, field: ExtractedFieldValue) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if field.confidence < CONFIDENCE_THRESHOLD:
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
