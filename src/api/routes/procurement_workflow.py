"""Authenticated UI-facing integration endpoints on the shared PR repository."""

import asyncio
import hashlib
import logging
from typing import get_args

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src.api.dependencies import require_role
from src.api.routes.evaluation import configure_evaluation
from src.application.procurement.workflow import ProcurementWorkflow
from src.core.config import get_settings
from src.domain.analysis.evaluation import Feedback
from src.domain.procurement.workflow import ProcurementAnalysis, ProcurementFeedbackResult, WorkflowStatus
from src.infrastructure.evaluation.evidence import PostgresEvidenceAdapter
from src.infrastructure.evaluation.embedding import LocalLexicalEmbeddings
from src.infrastructure.evaluation.store import ReviewConflictError, ReviewForbiddenError
from src.infrastructure.quotation.repository import get_quotation_repository
from src.infrastructure.repositories.purchase_orders import get_po_repository
from src.infrastructure.repositories.purchase_requests import get_pr_repository

router = APIRouter(tags=["procurement-workflow"])
logger = logging.getLogger(__name__)


class BuyerRecommendationSubmission(BaseModel):
    note: str | None = None


def initialize_procurement(app) -> ProcurementWorkflow:
    settings = get_settings()
    try:
        evidence = PostgresEvidenceAdapter(
            settings.database_url,
            LocalLexicalEmbeddings(),
            k=settings.evidence_query_k,
        )
    except (psycopg.Error, OSError):
        logger.exception(
            "Vector database initialization failed",
            extra={"event": "vector_database_connection_failed", "storage_backend": "postgresql"},
        )
        raise
    logger.info(
        "Vector database initialized",
        extra={"event": "vector_database_initialized", "storage_backend": "postgresql"},
    )
    # Context is resolved from persisted application snapshots, never from LLM/request policy.
    workflow = configure_evaluation(
        app,
        evidence,
        lambda case, actor: app.state.procurement_workflow.context(case, actor),
    )
    service = ProcurementWorkflow(
        settings.procurement_workflow_path,
        workflow,
        tenant_id=settings.procurement_tenant_id,
        running_timeout_seconds=settings.analysis_running_timeout_seconds,
    )
    service.migrate_legacy_runs(get_pr_repository())
    app.state.procurement_workflow = service
    app.state.evidence_adapter = evidence
    return service


def get_procurement_workflow(request: Request) -> ProcurementWorkflow:
    return getattr(request.app.state, "procurement_workflow", None) or initialize_procurement(request.app)


def require_pr(pr_id, repository):
    pr = repository.get(pr_id)
    if pr is None:
        raise HTTPException(404, "Không tìm thấy PR.")
    return pr


async def _run_analysis_in_background(service: ProcurementWorkflow, start) -> None:
    """Keep the event loop free while graph/LLM work uses a worker thread."""
    await run_in_threadpool(service.execute_analysis, start)


def _analysis_response(run: dict, status_code: int) -> JSONResponse:
    # Validate the public contract before bypassing FastAPI's response-model
    # machinery for a dynamic 200/202 response.  ``None`` event telemetry is
    # intentionally retained so an absent provider token count is explicit.
    payload = ProcurementAnalysis.model_validate(public_run(run)).model_dump(mode="json")
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


@router.post("/prs/{pr_id}/analysis", response_model=ProcurementAnalysis)
async def analyze(
    pr_id: str,
    request: Request,
    force: bool = Query(default=False, description="Bỏ qua cache kết quả của snapshot hiện tại."),
    user=Depends(require_role("procurement")),
    prs=Depends(get_pr_repository),
    quotes=Depends(get_quotation_repository),
    service=Depends(get_procurement_workflow),
):
    pr = require_pr(pr_id, prs)
    if pr.status not in {"awaiting_quotation", "comparing"}:
        raise HTTPException(409, "PR hiện không thể chạy phân tích mới.")
    start = await run_in_threadpool(service.start_analysis, pr, quotes.list_for_pr(pr_id), force=force)
    if start.input_error is not None:
        # The repairable run was persisted, so the frontend can immediately
        # fetch and render its field-level guidance after this 422 response.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(start.input_error))
    if not start.should_execute:
        return _analysis_response(start.run, status.HTTP_200_OK)

    task = asyncio.create_task(_run_analysis_in_background(service, start))
    tasks = getattr(request.app.state, "procurement_analysis_tasks", set())
    tasks.add(task)
    request.app.state.procurement_analysis_tasks = tasks
    task.add_done_callback(tasks.discard)
    return _analysis_response(start.run, status.HTTP_202_ACCEPTED)


class CancelAnalysisRequest(BaseModel):
    analysis_id: str = Field(min_length=1, max_length=64)


@router.post("/prs/{pr_id}/analysis/cancel", response_model=ProcurementAnalysis)
def cancel_analysis(
    pr_id: str,
    payload: CancelAnalysisRequest,
    user=Depends(require_role("procurement")),
    prs=Depends(get_pr_repository),
    service=Depends(get_procurement_workflow),
):
    del user
    require_pr(pr_id, prs)
    try:
        run = service.cancel_analysis(pr_id, payload.analysis_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return public_run(run)


def public_run(run):
    """Expose only the current public analysis contract.

    Analysis rows are durable and may retain telemetry or private source
    snapshots from an older schema.  The response model is deliberately strict,
    so filtering by its declared fields keeps a historical row readable without
    leaking internal data or producing a response-validation 500.
    """
    payload = {key: value for key, value in run.items() if key in ProcurementAnalysis.model_fields}
    if payload.get("status") not in get_args(WorkflowStatus):
        payload["status"] = "stale"
        payload["message"] = "Đề xuất cũ chưa được kiểm chứng. Hãy phân tích lại trước khi gửi duyệt."
    # The graph produces strict agent artifacts while this browser API still
    # exposes the established public procurement contract.  Project at this
    # boundary so durable v1 fields (revision IDs, currency and breakdowns)
    # never leak into — or break validation of — the legacy response model.
    if "tco_results" in payload:
        payload["tco_results"] = [_public_tco_result(item) for item in payload["tco_results"]]
    if "risk_flags" in payload:
        payload["risk_flags"] = [_public_risk_flag(item) for item in payload["risk_flags"]]
    return payload


def _public_tco_result(item: object) -> object:
    if not isinstance(item, dict):
        return item
    breakdown = item.get("items_tco", item.get("breakdown", []))
    return {
        "supplier_id": item.get("supplier_id"),
        "items_tco": [_public_tco_item(line) for line in breakdown],
        "subtotal": item.get("subtotal", 0),
        "total_surcharges": item.get("total_surcharges", 0),
        "total_vat": item.get("total_vat", 0),
        "total_tco": item.get("total_tco"),
        "status": item.get("status"),
        "missing_fields": item.get("missing_fields", []),
    }


def _public_tco_item(item: object) -> object:
    if not isinstance(item, dict):
        return item
    return {
        "item_name": item.get("item_name", item.get("product_name", "")),
        "quantity": item.get("quantity"),
        "unit_price": item.get("unit_price"),
        "subtotal": item.get("subtotal", 0),
        "surcharges": item.get("surcharges", 0),
        "vat_rate": item.get("vat_rate", 0),
        "vat_included": item.get("vat_included", False),
        "item_tco": item.get("item_tco"),
    }


def _public_risk_flag(item: object) -> object:
    if not isinstance(item, dict):
        return item
    severity = item.get("severity", "warning")
    return {
        "supplier_id": item.get("supplier_id"),
        "risk_type": item.get("risk_type"),
        "severity": {"low": "info", "medium": "warning", "high": "error", "critical": "error"}.get(severity, severity),
        "message": item.get("message", item.get("description", "Rủi ro cần được xem xét.")),
        "detail": item.get("detail", item.get("details", {})),
        "source": item.get("source"),
    }


def stale_run_if_snapshot_changed(run, pr, quotes, service):
    """Do not present a cached input/error state after a quotation was edited."""
    snapshot_revision = run.get("snapshot_revision")
    if not isinstance(snapshot_revision, str) or not snapshot_revision:
        return run
    quotation_rows = quotes.list_for_pr(pr.id)
    run = service.refresh_legacy_snapshot_revision(run, pr, quotation_rows)
    snapshot_revision = run.get("snapshot_revision")
    current_revision = service.revision(pr, quotation_rows)
    if snapshot_revision == current_revision:
        return run
    return {
        **run,
        "status": "stale",
        "message": "Dữ liệu PR hoặc báo giá đã thay đổi. Hãy chạy lại phân tích.",
        "missing_fields": [],
        "recommendation_id": None,
        "recommendation_version": None,
        "review": None,
        "evaluation": None,
        "tco_results": [],
        "comparison_matrix": {},
        "risk_flags": [],
    }


@router.get("/prs/{pr_id}/analysis", response_model=ProcurementAnalysis)
def analysis(
    pr_id: str,
    user=Depends(require_role("procurement", "manager")),
    prs=Depends(get_pr_repository),
    service=Depends(get_procurement_workflow),
    quotes=Depends(get_quotation_repository),
):
    pr = require_pr(pr_id, prs)
    run = stale_run_if_snapshot_changed(service.latest(pr_id), pr, quotes, service)
    # Historical runs written before the confirmed-quotation adapter could
    # incorrectly be labelled as awaiting Buyer review although their decision
    # explicitly said it needed input.  Present that state truthfully and let
    # the normal retry endpoint regenerate the same snapshot.
    proposal = run.get("review") or run.get("decision_proposal") or {}
    if run["status"] == "awaiting_buyer_review" and proposal.get("status") == "needs_input":
        run.update(
            status="needs_input",
            message=proposal.get("rationale", "Thiếu dữ liệu để tạo đề xuất."),
            review=None,
        )
    if run["status"] == "awaiting_buyer_review":
        try:
            service.ensure_current(run, prs, quotes)
        except ReviewConflictError:
            run.update(
                status="needs_input",
                message="Dữ liệu đã thay đổi. Xác nhận các báo giá rồi phân tích lại.",
                review=None,
                evaluation=None,
                tco_results=[],
                comparison_matrix={},
                risk_flags=[],
            )
    return {**public_run(run), "pr": pr.model_dump(mode="json")}


@router.get("/recommendations/{recommendation_id}/review")
def review(
    recommendation_id: str,
    user=Depends(require_role("procurement", "manager")),
    prs=Depends(get_pr_repository),
    quotes=Depends(get_quotation_repository),
    service=Depends(get_procurement_workflow),
):
    try:
        run = service.by_recommendation(recommendation_id)
        service.ensure_current(run, prs, quotes)
        # Buyers may inspect the verified renderer but cannot finalize a review.
        if user.role == "procurement":
            if run["status"] != "awaiting_buyer_review":
                raise ReviewConflictError("Đề xuất hiện không chờ review.")
            return run["review"]
        if run["status"] not in {"pending_manager_approval", "approved"}:
            raise ReviewConflictError("Recommendation is not available for Manager review.")
        return run["review"]
    except ReviewForbiddenError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ReviewConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/recommendations/{recommendation_id}/sources/{quotation_id}")
def review_source(
    recommendation_id: str,
    quotation_id: str,
    user=Depends(require_role("procurement", "manager")),
    prs=Depends(get_pr_repository),
    quotes=Depends(get_quotation_repository),
    service=Depends(get_procurement_workflow),
) -> Response:
    try:
        run = service.by_recommendation(recommendation_id)
        if run["status"] not in {"awaiting_buyer_review", "pending_manager_approval", "approved"}:
            raise ReviewConflictError("Chỉ tải nguồn của đề xuất đã kiểm chứng.")
        if run["status"] in {"awaiting_buyer_review", "pending_manager_approval"}:
            service.ensure_current(run, prs, quotes)
        if quotation_id not in {q["id"] for q in run["quotations"]}:
            raise HTTPException(404, "Báo giá không thuộc snapshot đề xuất này.")
        quote = quotes.get(quotation_id)
        if quote is None or quote.pr_id != run["pr_id"] or not quotes.source_exists(quote):
            raise HTTPException(404, "Không tìm thấy file nguồn.")
        expected = run["context"]["source_scope"]["document_hashes"][quotation_id]
        if hashlib.sha256(quotes.read_source(quote)).hexdigest() != expected:
            raise ReviewConflictError("File nguồn không còn khớp snapshot đã kiểm chứng.")
        return Response(
            content=quotes.read_source(quote),
            media_type=quote.source_content_type,
            headers={"Content-Disposition": f'attachment; filename="{quote.source_filename}"'},
        )
    except ReviewConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/analyses/{analysis_id}/submit-approval")
def submit_recommendation_for_approval(
    analysis_id: str,
    payload: BuyerRecommendationSubmission,
    user=Depends(require_role("procurement")),
    service=Depends(get_procurement_workflow),
    prs=Depends(get_pr_repository),
    quotes=Depends(get_quotation_repository),
):
    try:
        current = service.by_analysis(analysis_id)
        service.ensure_current(current, prs, quotes)
        submitted_pr = prs.submit_for_approval(current["pr_id"])
        if submitted_pr is None:
            raise ReviewConflictError("Không tìm thấy PR để gửi phê duyệt.")
        run = service.submit_buyer_review(analysis_id, user, payload.note)
        logger.info(
            "Buyer submitted recommendation for approval",
            extra={
                "event": "buyer_review_submitted",
                "actor_id": user.id,
                "actor_role": user.role,
                "resource": "analysis",
                "resource_id": analysis_id,
                "new_status": run["status"],
            },
        )
        return {
            **run["buyer_confirmation"],
            "status": run["status"],
            "pr_status": submitted_pr.status,
        }
    except ReviewConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post(
    "/recommendations/{recommendation_id}/feedback",
    response_model=ProcurementFeedbackResult,
    response_model_exclude_none=True,
)
def feedback(
    recommendation_id: str,
    payload: Feedback,
    user=Depends(require_role("manager")),
    prs=Depends(get_pr_repository),
    quotes=Depends(get_quotation_repository),
    pos=Depends(get_po_repository),
    service=Depends(get_procurement_workflow),
):
    if payload.recommendation_id != recommendation_id:
        raise HTTPException(409, "Recommendation ID không khớp URL.")
    try:
        result = service.feedback(payload, user, prs, quotes, pos)
        logger.info(
            "Buyer review decision applied",
            extra={
                "event": f"buyer_review_{payload.decision}",
                "actor_id": user.id,
                "actor_role": user.role,
                "resource": "recommendation",
                "resource_id": recommendation_id,
                "new_status": result.get("status"),
            },
        )
        return result
    except ReviewForbiddenError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ReviewConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
