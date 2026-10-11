from __future__ import annotations

from typing import Final

from langgraph.types import interrupt
from pydantic import TypeAdapter

from src.agents.state import ProcurementAgentState
from src.models_v1.quotation.confirmation import QuotationConfirmationRequest
from src.models_v1.quotation.extraction import ExtractionDraftPayload

CONFIRMATION_LIST_ADAPTER: Final = TypeAdapter(list[QuotationConfirmationRequest])


class ConfirmationCountError(ValueError):
    __slots__ = ("actual", "expected")

    expected: int
    actual: int

    def __init__(self, *, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"Expected {self.expected} quotation confirmations, received {self.actual}"


class UnknownSourceItemError(ValueError):
    __slots__ = ("source_item_id",)

    source_item_id: str

    def __init__(self, *, source_item_id: str) -> None:
        self.source_item_id = source_item_id
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"Confirmed source item does not belong to its extraction draft: {self.source_item_id}"


def human_review_extraction(state: ProcurementAgentState) -> ProcurementAgentState:
    """Pause for mandatory Buyer confirmation of every models_v1 extraction draft."""
    drafts = [ExtractionDraftPayload.model_validate(raw) for raw in state.get("raw_extractions", [])]
    response = interrupt(
        {
            "checkpoint": "extraction_review",
            "review_mode": "mandatory",
            "drafts": [draft.model_dump(mode="json") for draft in drafts],
            "validations": [
                validation.model_dump(mode="json") for validation in state.get("validated_extractions", [])
            ],
        }
    )
    confirmations = CONFIRMATION_LIST_ADAPTER.validate_python(response)
    if len(confirmations) != len(drafts):
        raise ConfirmationCountError(expected=len(drafts), actual=len(confirmations))
    for draft, confirmation in zip(drafts, confirmations, strict=True):
        source_item_ids = {item.source_item_id for item in draft.items}
        for item in confirmation.items:
            if item.source_item_id is not None and item.source_item_id not in source_item_ids:
                raise UnknownSourceItemError(source_item_id=item.source_item_id)
    return {"confirmed_quotes": confirmations}
