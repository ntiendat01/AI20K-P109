"""Deprecated import bridge; use ``src.models.quotation.extraction``."""

from src.models.quotation.extraction import (
    BatchExtractionResult,
    ExtractedPage,
    ExtractionResult,
    ExtractionStatus,
)
from src.models.quotation.extraction import (
    ExtractedQuotation as Quotation,
)
from src.models.quotation.extraction import (
    ExtractedQuotationItem as QuotationItem,
)

__all__ = [
    "BatchExtractionResult",
    "ExtractedPage",
    "ExtractionResult",
    "ExtractionStatus",
    "Quotation",
    "QuotationItem",
]
