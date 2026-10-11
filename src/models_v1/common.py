"""Shared primitives, types, and base models for the procurement contracts v1.

All models in models_v1 follow strict contract principles:
- Immutable (frozen=True) by default for entities, revisions, and artifacts.
- Decimal string serialization for money, quantities, and rates across boundaries.
- Explicit UTC awareness for all timestamps.
- Extra fields forbidden (extra='forbid') to ensure schema rigor.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
)


def _ensure_utc(val: datetime) -> datetime:
    """Ensure aware datetime is converted to UTC timezone."""
    if val.tzinfo is None:
        return val.replace(tzinfo=UTC)
    return val.astimezone(UTC)


UtcDateTime = Annotated[
    AwareDatetime,
    AfterValidator(_ensure_utc),
    PlainSerializer(
        lambda dt: dt.isoformat().replace("+00:00", "Z"),
        return_type=str,
        when_used="json",
    ),
]

ConfidenceScore = Annotated[
    Decimal,
    Field(ge=0, le=1),
    PlainSerializer(
        lambda v: f"{v:.2f}" if v == v.quantize(Decimal("0.01")) else str(v),
        return_type=str,
        when_used="json",
    ),
]

Quantity = Annotated[
    Decimal,
    Field(gt=0),
    PlainSerializer(
        lambda v: str(v),
        return_type=str,
        when_used="json",
    ),
]

Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=18, decimal_places=2),
    PlainSerializer(
        lambda v: f"{v:.2f}",
        return_type=str,
        when_used="json",
    ),
]

VatRate = Annotated[
    Decimal,
    Field(ge=0, le=1),
    PlainSerializer(
        lambda v: f"{v:.2f}",
        return_type=str,
        when_used="json",
    ),
]


class ContractModel(BaseModel):
    """Immutable base model with strict schema validation defaults."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )


class MutableContractModel(BaseModel):
    """Mutable contract model for scratch/builder states where needed."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        populate_by_name=True,
    )


class ErrorDetails(ContractModel):
    """Standardized error details compliant with API contracts."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class ErrorResponse(ContractModel):
    """Top-level error envelope for all HTTP error responses."""

    error: ErrorDetails


__all__ = [
    "ConfidenceScore",
    "ContractModel",
    "ErrorDetails",
    "ErrorResponse",
    "Money",
    "MutableContractModel",
    "Quantity",
    "UtcDateTime",
    "VatRate",
]
