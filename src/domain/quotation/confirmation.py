"""Schemas for Buyer-confirmed quotation data used by analysis."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from src.domain.common import ContractModel
from src.domain.fuzzy_match import MatchStatus


class QuotationStatus(StrEnum):
    """Describe whether a quotation is waiting for or has Buyer confirmation."""

    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"


class QuotationItem(ContractModel):
    """Represent one commercial item explicitly confirmed by the Buyer."""

    product_name: str = Field(min_length=1, max_length=500)
    product_code: str = Field(default="", max_length=100)
    unit: str = Field(default="", max_length=100)
    quantity: int = Field(gt=0, le=1_000_000)
    unit_price: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    line_total: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    matched_pr_item_id: str | None = None
    match_status: MatchStatus | None = None


class QuotationConfirmation(ContractModel):
    """Validate the complete Buyer payload used to confirm a quotation."""

    supplier_name: str = Field(min_length=2, max_length=200)
    delivery_time: str = Field(default="", max_length=500)
    payment_terms: str = Field(default="", max_length=1000)
    items: list[QuotationItem] = Field(min_length=1, max_length=100)
    currency: str | None = None
    vat_rate: Decimal = Field(ge=0, le=1)
    vat_included: bool
    shipping_fee: Decimal = Field(ge=0)
    lead_time_days: int = Field(ge=0)
    warranty_months: int = Field(ge=0)
    goods_total_including_tax: Decimal | None = Field(default=None, ge=0)
    shipping_total_including_tax: Decimal | None = Field(default=None, ge=0)


class ConfirmedQuotation(ContractModel):
    """Represent the confirmed quotation snapshot consumed by normalization."""

    supplier_id: str | None = None
    id: str
    pr_id: str
    supplier_name: str
    source_filename: str
    source_hash: str
    source_path: str = Field(exclude=True)
    source_content_type: str
    extraction_version: int = Field(default=1, ge=1)
    delivery_time: str = ""
    payment_terms: str = ""
    warranty: str = ""
    currency: str = ""
    items: list[QuotationItem] = Field(default_factory=list)
    status: QuotationStatus = QuotationStatus.UNCONFIRMED
    extraction_warnings: list[str] = Field(default_factory=list)
    cache_hit: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    confirmed_at: datetime | None = None
    vat_rate: Decimal | None = Field(default=None, ge=0, le=1)
    vat_included: bool | None = None
    shipping_fee: Decimal | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    warranty_months: int | None = Field(default=None, ge=0)
    goods_total_including_tax: Decimal | None = Field(default=None, ge=0)
    shipping_total_including_tax: Decimal | None = Field(default=None, ge=0)
    confirmation_audit: dict | None = Field(default=None, exclude=True)
    extraction_mode: str = "parser"
    agent_extractions: list[dict] = Field(default_factory=list)
    source_ocr_text: str | None = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def unwrap_legacy_currency(cls, value: object) -> object:
        """Read pre-contract extraction snapshots without altering their source files.

        An earlier extraction boundary persisted field evidence as
        ``{"value": "VND", ...}``, while the quotation contract has always
        exposed ``currency`` as a string.  Preserve the evidence in its native
        workflow storage, but normalize this one legacy quotation field at the
        repository boundary so one old draft cannot prevent other quotations
        from loading.
        """
        if not isinstance(value, dict):
            return value
        currency = value.get("currency")
        if isinstance(currency, dict) and isinstance(currency.get("value"), str):
            return {**value, "currency": currency["value"]}
        return value


Quotation = ConfirmedQuotation
__all__ = ["ConfirmedQuotation", "Quotation", "QuotationConfirmation", "QuotationItem", "QuotationStatus"]
