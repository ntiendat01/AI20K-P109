"""Authenticated integration seam for the downstream workflow, with no client policy input."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import JsonValue

from src.models.evaluation import Actor, Contract, EvaluationResult, Feedback, FeedbackReceipt, RuntimeEvaluationContext
from src.services.evaluation.evidence import ChromaCollection
from src.services.evaluation.store import ReviewConflictError, ReviewForbiddenError
from src.services.evaluation.workflow import EvaluationWorkflow, RepairModel

router = APIRouter(prefix="/evaluations", tags=["evaluation"])


def configure_evaluation(
    app: FastAPI,
    collection: ChromaCollection,
    context_provider: Callable[[str, Actor], RuntimeEvaluationContext],
    *,
    repair_model: RepairModel | None = None,
) -> EvaluationWorkflow:
    """Install trusted application dependencies at startup; never infer policy from LLM state."""
    from src.core.config import get_settings
    from src.services.evaluation.engine import Evaluator
    from src.services.evaluation.evidence import ChromaEvidenceAdapter
    from src.services.evaluation.store import EvaluationStore

    settings = get_settings()
    workflow = EvaluationWorkflow(
        Evaluator(
            ChromaEvidenceAdapter(collection, k=settings.evidence_query_k),
            service_retries=settings.evidence_service_retries,
            backoff_seconds=settings.evidence_retry_backoff_seconds,
        ),
        EvaluationStore(settings.evaluation_database_path),
        repair_model,
    )
    app.state.evaluation_workflow = workflow
    app.state.evaluation_context_provider = context_provider
    return workflow


class EvaluationSubmission(Contract):
    proposal: JsonValue


def _workflow(request: Request) -> EvaluationWorkflow:
    workflow = getattr(request.app.state, "evaluation_workflow", None)
    if not isinstance(workflow, EvaluationWorkflow):
        raise HTTPException(503, "Post-decision evaluation is not configured")
    return workflow


def _actor(request: Request) -> Actor:
    # Only middleware may set request.state.actor; body/header role claims are ignored.
    actor = getattr(request.state, "actor", None)
    if not isinstance(actor, Actor):
        raise HTTPException(401, "Authenticated review context is required")
    return actor


@router.post("/cases/{case_id}", response_model=EvaluationResult)
def evaluate_output(case_id: str, submission: EvaluationSubmission, request: Request) -> EvaluationResult:
    actor = _actor(request)
    service = getattr(request.app.state, "procurement_workflow", None)
    if service is not None:
        raise HTTPException(409, "Dùng API phân tích PR để tạo đề xuất từ dữ liệu nghiệp vụ hiện hành.")
    provider = getattr(request.app.state, "evaluation_context_provider", None)
    if provider is None:
        raise HTTPException(503, "Runtime evaluation context is not configured")
    context = provider(case_id, actor)
    if not isinstance(context, RuntimeEvaluationContext) or context.case_id != case_id:
        raise HTTPException(503, "Invalid runtime evaluation context")
    try:
        EvaluationWorkflow._authorize(actor, context)
        return _workflow(request).submit(submission.proposal, context)
    except ReviewForbiddenError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ReviewConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{recommendation_id}/review")
def review_payload(recommendation_id: str, request: Request) -> dict[str, object]:
    actor = _actor(request)
    service = getattr(request.app.state, "procurement_workflow", None)
    if service is not None:
        from src.services.procurement.purchase_requests import get_pr_repository
        from src.services.quotation.repository import get_quotation_repository

        try:
            service.ensure_current(
                service.by_recommendation(recommendation_id), get_pr_repository(), get_quotation_repository()
            )
        except ReviewConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
    try:
        return _workflow(request).review_payload(recommendation_id, actor)
    except ReviewForbiddenError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ReviewConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{recommendation_id}/feedback", response_model=FeedbackReceipt)
def review_feedback(recommendation_id: str, feedback: Feedback, request: Request) -> FeedbackReceipt:
    actor = _actor(request)
    if feedback.recommendation_id != recommendation_id:
        raise HTTPException(409, "Feedback recommendation does not match URL")
    try:
        service = getattr(request.app.state, "procurement_workflow", None)
        if service is not None:
            from src.services.auth import get_session
            from src.services.procurement.purchase_orders import get_po_repository
            from src.services.procurement.purchase_requests import get_pr_repository
            from src.services.quotation.repository import get_quotation_repository

            user = get_session(request.headers["Authorization"].removeprefix("Bearer ")).user
            result = service.feedback(
                feedback, user, get_pr_repository(), get_quotation_repository(), get_po_repository()
            )
            return FeedbackReceipt.model_validate(result["receipt"])
        return _workflow(request).feedback(feedback, actor)
    except ReviewForbiddenError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ReviewConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
