from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Annotated, cast
from uuid import uuid4

import csv
import io
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from src.agents.graph import build_graph
from src.core.config import get_settings
from src.models.evaluation import AnalysisRunResponse
from src.models.pr import (
    DocumentUploadResponse,
    PRCreateRequest,
    PRResponse,
)
from src.models.procurement import DecisionPipelineResponse, PRData



MAX_DOCUMENTS = 10
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024

router = APIRouter(prefix="/prs", tags=["procurement"])


@dataclass(frozen=True, slots=True)
class StoredDocument:
    """Metadata for a PDF persisted on local storage."""

    filename: str
    path: str
    size_bytes: int


@dataclass(slots=True)
class StoredCase:
    """Procurement case retained until a persistent store is introduced."""

    request: PRCreateRequest
    documents: list[StoredDocument] = field(default_factory=list)


case_store: dict[str, StoredCase] = {}


def _get_case(case_id: str) -> StoredCase:
    try:
        return case_store[case_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Procurement case not found") from exc


@router.post("", response_model=PRResponse, status_code=status.HTTP_201_CREATED)
async def create_pr(request: PRCreateRequest) -> PRResponse:
    """Create a procurement case awaiting quote documents."""
    case_id = str(uuid4())
    case_store[case_id] = StoredCase(request=request)
    return PRResponse(
        case_id=case_id,
        pr_number=request.pr_number,
        quantity=request.quantity,
        deadline=request.deadline,
        budget=request.budget,
        status="awaiting_documents",
        same_day_deadline=request.deadline == date.today(),
        document_count=0,
    )





@router.post(
    "/{case_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    case_id: str,
    file: Annotated[UploadFile, File(description="PDF supplier quote")],
) -> DocumentUploadResponse:
    """Validate and retain one PDF quote, up to ten per case."""
    procurement_case = _get_case(case_id)
    if len(procurement_case.documents) >= MAX_DOCUMENTS:
        raise HTTPException(status_code=400, detail="Tối đa 10 báo giá mỗi PR")

    filename = Path(file.filename or "").name
    if file.content_type != "application/pdf" or Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file PDF")

    content = await file.read(MAX_FILE_SIZE_BYTES + 1)
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File PDF không được vượt quá 2 MB")

    case_directory = get_settings().upload_dir / case_id
    case_directory.mkdir(parents=True, exist_ok=True)
    document_path = case_directory / f"{uuid4().hex}_{filename}"
    document_path.write_bytes(content)
    procurement_case.documents.append(
        StoredDocument(
            filename=filename,
            path=str(document_path.resolve()),
            size_bytes=len(content),
        )
    )
    return DocumentUploadResponse(
        case_id=case_id,
        status="uploaded",
        filename=filename,
        size_bytes=len(content),
        document_count=len(procurement_case.documents),
    )


@router.post("/{case_id}/analyze", response_model=AnalysisRunResponse, deprecated=True)
async def analyze_pr(case_id: str, request: Request) -> AnalysisRunResponse:
    """Run analysis to its durable review boundary; never approve on behalf of a buyer."""
    procurement_case = _get_case(case_id)
    document_count = len(procurement_case.documents)
    if document_count < 2:
        missing = 2 - document_count
        raise HTTPException(status_code=400, detail=f"Cần thêm {missing} báo giá")

    pr_request = procurement_case.request
    pr_data = PRData(
        pr_number=pr_request.pr_number,
        quantity=pr_request.quantity,
        deadline=pr_request.deadline,
        budget=pr_request.budget,
    )
    initial_state: dict[str, object] = {
        "case_id": case_id,
        "pr_data": pr_data.model_dump(mode="json"),
        "documents": [document.path for document in procurement_case.documents],
    }
    config: RunnableConfig = {"configurable": {"thread_id": case_id}}

    try:
        graph = build_graph()
        result = await _run_analysis(initial_state, config, graph)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Procurement analysis failed") from exc

    return AnalysisRunResponse(
        case_id=case_id,
        status=result.get("workflow_status", "needs_input"),
        recommendation_id=result.get("recommendation_id"),
        recommendation_version=result.get("recommendation_version"),
        evaluation=result.get("evaluation_result") if result.get("recommendation_id") else None,
    )


@router.post("/{case_id}/decision-pipeline", response_model=DecisionPipelineResponse, deprecated=True)
async def run_decision_pipeline(case_id: str) -> DecisionPipelineResponse:
    """Run the secondary graph through extraction, normalization, and decision LLM."""
    procurement_case = _get_case(case_id)
    document_count = len(procurement_case.documents)
    if document_count < 1:
        raise HTTPException(status_code=400, detail="Cần ít nhất 1 báo giá để xử lý")

    request = procurement_case.request
    pr_data = PRData(
        pr_number=request.pr_number,
        quantity=request.quantity,
        deadline=request.deadline,
        budget=request.budget,
    )
    initial_state: dict[str, object] = {
        "case_id": case_id,
        "pr_data": pr_data.model_dump(mode="json"),
        "documents": [document.path for document in procurement_case.documents],
    }
    config: RunnableConfig = {"configurable": {"thread_id": f"decision_{case_id}"}}

    try:
        result = await _run_analysis(initial_state, config, build_graph())
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Decision pipeline execution failed") from exc

    return DecisionPipelineResponse.model_validate(
        {
            "case_id": case_id,
            "status": "awaiting_confirmation" if _interrupt_checkpoint(result) else "technical_failure",
            "raw_extractions": result.get("raw_extractions") or [],
            "normalized_quotes": result.get("normalized_quotes") or [],
            "tco_results": result.get("tco_results") or [],
            "comparison_matrix": result.get("comparison_matrix") or {},
            "risk_flags": result.get("risk_flags") or [],
            "decision_proposal": result.get("decision_proposal") or {},
        }
    )


async def _run_analysis(initial_state: dict[str, object], config: RunnableConfig, graph) -> dict[str, object]:
    """A legacy debug invocation never confirms any extraction."""
    result = cast(dict[str, object], await graph.ainvoke(initial_state, config))
    if _interrupt_checkpoint(result) == "extraction_review":
        result["workflow_status"] = "needs_input"
    return result


def _interrupt_checkpoint(result: Mapping[str, object]) -> str | None:
    interruptions = result.get("__interrupt__")
    if not isinstance(interruptions, (list, tuple)) or not interruptions:
        return None
    payload = getattr(interruptions[0], "value", None)
    if not isinstance(payload, Mapping):
        return None
    checkpoint = payload.get("checkpoint")
    return checkpoint if isinstance(checkpoint, str) else None
