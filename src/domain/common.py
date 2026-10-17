"""Shared primitives used by the confirmed procurement contracts."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
)


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDateTime = Annotated[AwareDatetime, AfterValidator(_as_utc)]
ConfidenceScore = Annotated[
    Decimal,
    Field(ge=0, le=1),
    PlainSerializer(str, return_type=str, when_used="json"),
]
Quantity = Annotated[
    Decimal,
    Field(gt=0),
    PlainSerializer(str, return_type=str, when_used="json"),
]
Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=18, decimal_places=2),
    PlainSerializer(str, return_type=str, when_used="json"),
]
VatRate = Annotated[
    Decimal,
    Field(ge=0, le=1),
    PlainSerializer(str, return_type=str, when_used="json"),
]


class ContractModel(BaseModel):
    """Provide strict validation defaults shared by all new public schemas."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)
