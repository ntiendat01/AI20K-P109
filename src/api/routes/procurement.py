import csv
import hashlib
import io
from pathlib import Path
from time import monotonic
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src.agents.graph import agent
from src.api.contracts.common import ChatRequest, ChatResponse, LoginRequest, LoginResponse, UserProfile
from src.api.dependencies import get_current_user, require_role
from src.application.procurement.comparison import build_comparison
from src.application.procurement.purchase_requests import (
    PurchaseRequestConflictError,
    PurchaseRequestLockedError,
    PurchaseRequestNotFoundError,
    PurchaseRequestPayloadError,
    preview_purchase_request_update,
)
from src.application.procurement.purchase_requests import update_purchase_request as apply_purchase_request_update
from src.application.quotation.intake import extract_for_quotation
from src.application.quotation.parser import EXTRACTION_VERSION, ExtractedQuotation, extract_quotation
from src.core.config import get_settings
from src.domain.fuzzy_match import BatchMatchResult, ConfirmMatchRequest, MatchAction, MatchCandidate, MatchStatus
from src.domain.matching import PRItem as FuzzyPRItem
from src.domain.matching import ProductMatchingService, QuoteItemInput
from src.domain.procurement.contracts import (
    PRComparisonResponse,
    PurchaseOrder,
    PurchaseOrderPage,
    Quotation,
    QuotationStatus,
)
from src.domain.procurement.invalidation import PurchaseRequestImpact
from src.domain.purchase_request import (
    PRStatus,
    PurchaseRequest,
    PurchaseRequestCreate,
    PurchaseRequestUpdate,
)
from src.domain.quotation.confirmation import QuotationConfirmation as BuyerQuotationConfirmation
from src.domain.quotation.extraction import BatchExtractionResult, ExtractionResult, ExtractionStatus
from src.infrastructure.auth import DemoUser, authenticate, create_session, revoke_session
from src.infrastructure.documents.service import process_pdf
from src.infrastructure.ocr.client import OCRServiceError
from src.infrastructure.quotation.pdf_review import build_review_preview, render_review_preview_page
from src.infrastructure.quotation.repository import QuotationRepository, get_quotation_repository
from src.infrastructure.repositories.purchase_orders import PurchaseOrderRepository, get_po_repository
from src.infrastructure.repositories.purchase_requests import PurchaseRequestRepository, get_pr_repository

router = APIRouter()

MAX_QUOTATION_FILE_BYTES = 5 * 1024 * 1024
MAX_QUOTATIONS_PER_PR = 10
MAX_BATCH_EXTRACTION_FILES = 5
SUPPORTED_QUOTATION_SUFFIXES = {".pdf", ".txt", ".eml"}


def quotation_extraction_jobs(app) -> dict:
    """Track the current upload so cancellation can discard an unfinished quote."""
    jobs = getattr(app.state, "quotation_extraction_jobs", None)
    if jobs is None:
        jobs = {"cancelled": {}, "active": {}}
        app.state.quotation_extraction_jobs = jobs
    now = monotonic()
    jobs["cancelled"] = {key: at for key, at in jobs["cancelled"].items() if now - at < 3600}
    return jobs


class CancelQuotationExtractionRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)


@router.post("/prs/{request_id}/quotations/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_quotation_extraction(
    request_id: str,
    payload: CancelQuotationExtractionRequest,
    http_request: Request,
    user: DemoUser = Depends(require_role("procurement")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> Response:
    del user
    if pr_repository.get(request_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy PR.")
    jobs = quotation_extraction_jobs(http_request.app)
    jobs["cancelled"][payload.job_id] = monotonic()
    active = jobs["active"].pop(payload.job_id, None)
    if active and active[0] == request_id:
        quotation_repository.delete(active[1])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/prs/{request_id}/extract", response_model=BatchExtractionResult)
async def extract_quotation_batch(
    request_id: str,
    files: list[UploadFile] = File(..., alias="files[]"),
    user: DemoUser = Depends(require_role("procurement")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
) -> BatchExtractionResult:
    """Return independent, unconfirmed extraction previews for up to five PDFs."""
    del user
    if pr_repository.get(request_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")
    if not 1 <= len(files) <= MAX_BATCH_EXTRACTION_FILES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Chọn từ 1 đến 5 file PDF.")

    results = []
    for file in files:
        name = Path(file.filename or "").name
        if Path(name).suffix.lower() != ".pdf":
            results.append(
                ExtractionResult(file_name=name, status=ExtractionStatus.FAILED, error="Chỉ hỗ trợ file PDF.")
            )
            continue
        content = await file.read(MAX_QUOTATION_FILE_BYTES + 1)
        if not content:
            results.append(
                ExtractionResult(file_name=name, status=ExtractionStatus.FAILED, error="File PDF đang trống.")
            )
        elif len(content) > MAX_QUOTATION_FILE_BYTES:
            results.append(
                ExtractionResult(file_name=name, status=ExtractionStatus.FAILED, error="File vượt quá giới hạn 5 MB.")
            )
        else:
            results.append(process_pdf(name, content))
    return BatchExtractionResult(quotations=results)


def user_profile(user: DemoUser) -> UserProfile:
    return UserProfile(id=user.id, name=user.name, email=user.email, role=user.role)


@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Đăng nhập bằng một trong hai tài khoản demo của MVP."""
    user = authenticate(request.email, request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không đúng.",
        )
    token, expires_at = create_session(user)
    return LoginResponse(access_token=token, expires_at=expires_at, user=user_profile(user))


@router.get("/auth/session", response_model=UserProfile)
async def current_session(user: DemoUser = Depends(get_current_user)) -> UserProfile:
    """Lấy người dùng của phiên hiện tại; frontend dùng để khôi phục phiên."""
    return user_profile(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    user: DemoUser = Depends(get_current_user),
    authorization: str | None = Header(default=None),
) -> Response:
    """Thu hồi token hiện tại."""
    del user  # Buộc endpoint đi qua xác thực trước khi thu hồi token.
    if authorization:
        revoke_session(authorization.removeprefix("Bearer "))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/procurement/workspace")
async def procurement_workspace(
    user: DemoUser = Depends(require_role("procurement")),
):
    """Endpoint mẫu để kiểm thử route guard của vai trò mua sắm."""
    return {"message": "Không gian làm việc mua sắm", "user": user.name}


@router.get("/manager/approvals")
async def manager_approvals(user: DemoUser = Depends(require_role("manager"))):
    """Endpoint mẫu để kiểm thử route guard của vai trò quản lý."""
    return {"message": "Danh sách PR chờ duyệt", "user": user.name}


@router.get("/manager/prs", response_model=list[PurchaseRequest])
async def list_manager_purchase_requests(
    user: DemoUser = Depends(require_role("manager")),
    repository: PurchaseRequestRepository = Depends(get_pr_repository),
) -> list[PurchaseRequest]:
    """List all PRs visible to manager dashboard and history filters."""
    del user
    return repository.list()


@router.get("/prs", response_model=list[PurchaseRequest])
async def list_purchase_requests(
    status_filter: PRStatus | None = Query(default=None, alias="status"),
    user: DemoUser = Depends(require_role("procurement")),
    repository: PurchaseRequestRepository = Depends(get_pr_repository),
) -> list[PurchaseRequest]:
    """Liệt kê PR của MVP, có thể lọc theo trạng thái."""
    del user
    return repository.list(status_filter)


@router.post("/prs", response_model=PurchaseRequest, status_code=status.HTTP_201_CREATED)
async def create_purchase_request(
    payload: PurchaseRequestCreate,
    is_draft: bool = Query(default=False, description="Tạo PR dưới dạng bản nháp (DRAFT)"),
    user: DemoUser = Depends(require_role("procurement")),
    repository: PurchaseRequestRepository = Depends(get_pr_repository),
) -> PurchaseRequest:
    """Tạo PR và chuyển từ Nháp sang Chờ báo giá khi lưu."""
    try:
        return repository.create(payload, user, is_draft)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


class BulkUploadError(BaseModel):
    row: int
    column: str | None = None
    message: str


@router.post("/prs/extract-items")
async def extract_items(file: UploadFile = File(description="CSV template bulk upload")):
    """Xử lý bulk upload cho PR items từ file CSV."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Hiện tại chỉ hỗ trợ file CSV")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # handle utf-8 with bom
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File CSV phải encode UTF-8")

    # Detect dialect
    try:
        dialect = csv.Sniffer().sniff(text[:1024])
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="File CSV trống")

    errors = []
    items = []
    for i, row in enumerate(reader, start=2):
        product_name = row.get("Tên sản phẩm", "").strip()
        quantity_str = row.get("Số lượng", "").strip()
        unit = row.get("Đơn vị", "").strip()
        notes = row.get("Ghi chú", "").strip()

        if not product_name:
            errors.append(BulkUploadError(row=i, column="Tên sản phẩm", message="Tên sản phẩm không được để trống"))

        if not quantity_str:
            errors.append(BulkUploadError(row=i, column="Số lượng", message="Số lượng không được để trống"))
        else:
            try:
                quantity = int(quantity_str)
                if quantity <= 0:
                    errors.append(BulkUploadError(row=i, column="Số lượng", message="Số lượng phải lớn hơn 0"))
            except ValueError:
                errors.append(BulkUploadError(row=i, column="Số lượng", message="Số lượng không hợp lệ"))

        if not unit:
            errors.append(BulkUploadError(row=i, column="Đơn vị", message="Đơn vị không được để trống"))

        if not errors:
            items.append(
                {
                    "product_name": product_name,
                    "quantity": quantity_str,
                    "unit": unit,
                    "notes": notes,
                    "order_index": i - 1,
                }
            )

    if errors:
        return {"valid_items": items, "errors": [e.model_dump(mode="json") for e in errors]}

    return {"valid_items": items}


@router.get("/prs/{request_id}", response_model=PurchaseRequest)
async def get_purchase_request(
    request_id: str,
    user: DemoUser = Depends(require_role("procurement")),
    repository: PurchaseRequestRepository = Depends(get_pr_repository),
) -> PurchaseRequest:
    """Xem chi tiết PR và số báo giá đã đính kèm."""
    del user
    request = repository.get(request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")
    return request


@router.patch("/prs/{request_id}", response_model=PurchaseRequest)
async def update_purchase_request(
    request_id: str,
    payload: PurchaseRequestUpdate,
    expected_version: int | None = Query(default=None, ge=1),
    user: DemoUser = Depends(require_role("procurement")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> PurchaseRequest:
    """Update a PR and apply the server-owned downstream invalidation policy."""
    try:
        result = apply_purchase_request_update(
            request_id,
            payload,
            pr_repository=pr_repository,
            quotation_repository=quotation_repository,
            actor_id=user.id,
            actor_role=user.role,
            expected_version=expected_version,
        )
    except PurchaseRequestNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except PurchaseRequestPayloadError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except (PurchaseRequestLockedError, PurchaseRequestConflictError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return result.request


@router.post("/prs/{request_id}/change-impact", response_model=PurchaseRequestImpact)
async def preview_pr_change_impact(
    request_id: str,
    payload: PurchaseRequestUpdate,
    user: DemoUser = Depends(require_role("procurement")),
    repository: PurchaseRequestRepository = Depends(get_pr_repository),
) -> PurchaseRequestImpact:
    """Return the authoritative reset scope before the Buyer confirms an edit."""
    del user
    request = repository.get(request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")
    try:
        _, impact = preview_purchase_request_update(request, payload)
    except PurchaseRequestPayloadError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return impact


@router.delete("/prs/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_purchase_request(
    request_id: str,
    user: DemoUser = Depends(require_role("procurement")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> Response:
    """Permanently delete a PR, every quotation and every uploaded source file."""
    del user
    pr = pr_repository.get(request_id)
    if pr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")
    if pr.status in {PRStatus.PENDING_APPROVAL, PRStatus.APPROVED}:
        raise HTTPException(409, "Không xóa PR đang chờ duyệt hoặc đã có PO. Cần giữ nguồn và lịch sử phê duyệt.")
    try:
        quotation_repository.delete_for_pr(request_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    pr_repository.delete(request_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/prs/{request_id}/comparison", response_model=PRComparisonResponse, deprecated=True)
async def get_pr_comparison(
    request_id: str,
    user: DemoUser = Depends(require_role("procurement", "manager")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> PRComparisonResponse:
    """Legacy MCDA comparison for reference; official review uses the evaluated analysis API."""
    del user
    pr = pr_repository.get(request_id)
    if pr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")
    quotations = quotation_repository.list_for_pr(request_id)
    try:
        return build_comparison(pr, quotations)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.get("/approvals", response_model=list[PurchaseRequest])
async def list_prs_pending_approval(
    user: DemoUser = Depends(require_role("manager")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
) -> list[PurchaseRequest]:
    """Danh sách các PR đang chờ Quản lý phê duyệt (Spec 4.6)."""
    del user
    return pr_repository.list(status=PRStatus.PENDING_APPROVAL)


@router.get("/pos", response_model=list[PurchaseOrder])
async def list_purchase_orders(
    user: DemoUser = Depends(require_role("manager", "procurement")),
    po_repository: PurchaseOrderRepository = Depends(get_po_repository),
) -> list[PurchaseOrder]:
    """Danh sách các Đơn mua hàng (PO nháp) đã được duyệt (Spec 4.6)."""
    del user
    return po_repository.list()


@router.get("/pos/page", response_model=PurchaseOrderPage)
async def list_purchase_orders_page(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    query: str = Query("", max_length=200),
    supplier: str = Query("", max_length=200),
    sort_by: Literal["code", "pr_code", "supplier_name", "approver_name", "approved_at", "total_amount"] = "approved_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    user: DemoUser = Depends(require_role("manager", "procurement")),
    po_repository: PurchaseOrderRepository = Depends(get_po_repository),
) -> PurchaseOrderPage:
    """Return a server-filtered page of approved draft purchase orders."""
    del user
    return po_repository.list_page(
        page=page,
        page_size=page_size,
        query=query,
        supplier=supplier,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )


@router.get("/pos/{po_id}", response_model=PurchaseOrder)
async def get_purchase_order(
    po_id: str,
    user: DemoUser = Depends(require_role("manager", "procurement")),
    po_repository: PurchaseOrderRepository = Depends(get_po_repository),
) -> PurchaseOrder:
    """Chi tiết một Đơn mua hàng (PO nháp) (Spec 4.6)."""
    del user
    po = po_repository.get(po_id)
    if po is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PO.")
    return po


@router.post("/prs/{request_id}/quotations", response_model=Quotation, status_code=status.HTTP_201_CREATED)
async def upload_quotation(
    request_id: str,
    http_request: Request,
    file: UploadFile = File(...),
    supplier_name: str = Form(default="", max_length=200),
    extraction_mode: str | None = Form(default=None),
    extraction_job_id: str | None = Form(default=None, max_length=64),
    user: DemoUser = Depends(require_role("procurement")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> Quotation:
    """Upload một PDF/TXT/EML và trả về bản trích xuất chưa xác nhận.

    supplier_name là tùy chọn — nếu không nhập, tên NCC sẽ được trích xuất
    tự động từ nội dung file bằng OCR/parser.
    """
    del user
    request = pr_repository.get(request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")
    if request.status not in {PRStatus.AWAITING_QUOTATION, PRStatus.COMPARING}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PR hiện không thể nhận thêm báo giá.")
    if len(quotation_repository.list_for_pr(request_id)) >= MAX_QUOTATIONS_PER_PR:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Mỗi PR chỉ được upload tối đa {MAX_QUOTATIONS_PER_PR} báo giá.",
        )

    source_filename = Path(file.filename or "").name
    suffix = Path(source_filename).suffix.lower()
    if suffix not in SUPPORTED_QUOTATION_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Chỉ hỗ trợ file PDF, TXT hoặc EML.",
        )
    content = await file.read(MAX_QUOTATION_FILE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File báo giá đang trống.")
    if len(content) > MAX_QUOTATION_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File vượt quá giới hạn 5 MB.",
        )

    mode = extraction_mode or get_settings().quotation_extraction_mode
    if mode not in {"parser", "agent"}:
        raise HTTPException(422, "Chọn cách đọc báo giá hợp lệ.")
    if mode == "agent" and suffix != ".pdf":
        raise HTTPException(415, "Chế độ AI hiện hỗ trợ PDF.")
    jobs = quotation_extraction_jobs(http_request.app) if extraction_job_id else None
    if jobs and extraction_job_id in jobs["cancelled"]:
        raise HTTPException(status_code=409, detail="Tiến trình trích xuất đã được ngừng.")
    source_hash = hashlib.sha256(content).hexdigest()
    cached = quotation_repository.cached_extraction(source_hash, EXTRACTION_VERSION)
    if mode == "agent":
        extracted = ExtractedQuotation()
    elif cached:
        extracted = ExtractedQuotation(
            supplier_name=cached.supplier_name,
            delivery_time=cached.delivery_time,
            payment_terms=cached.payment_terms,
            warranty=cached.warranty,
            currency=cached.currency,
            items=cached.items,
            warnings=cached.extraction_warnings,
        )
    else:
        try:
            extracted = extract_quotation(content, suffix)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        except OCRServiceError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error

    # Ưu tiên: tên NCC do user nhập > tên trích xuất từ OCR > tên file gốc
    resolved_supplier = (
        supplier_name.strip()
        or extracted.supplier_name
        or Path(source_filename).stem.replace("_", " ").replace("-", " ").title()
    )

    saved = quotation_repository.save_upload(
        pr_id=request_id,
        supplier_name=resolved_supplier,
        source_filename=source_filename,
        source_content_type=file.content_type or "application/octet-stream",
        content=content,
        extracted=extracted,
        cache_hit=mode == "parser" and cached is not None,
        extraction_version=EXTRACTION_VERSION,
    )

    if mode == "agent":
        if jobs and extraction_job_id:
            jobs["active"][extraction_job_id] = (request_id, saved.id)
        try:
            with quotation_repository.materialize_source(saved) as source_path:
                local_quotation = saved.model_copy(update={"source_path": str(source_path)})
                extracted, raw, ocr_text = await run_in_threadpool(
                    extract_for_quotation,
                    local_quotation,
                    ocr=getattr(http_request.app.state, "intake_ocr", None),
                    extractor=getattr(http_request.app.state, "intake_extractor", None),
                )
            if jobs and extraction_job_id in jobs["cancelled"]:
                quotation_repository.delete(saved.id)
                raise HTTPException(status_code=409, detail="Tiến trình trích xuất đã được ngừng.")
            return quotation_repository.apply_agent_extraction(saved.id, extracted, raw, ocr_text)
        except Exception:
            quotation_repository.delete(saved.id)
            raise
        finally:
            if jobs and extraction_job_id and jobs["active"].get(extraction_job_id) == (request_id, saved.id):
                jobs["active"].pop(extraction_job_id, None)
    return saved


@router.get("/prs/{request_id}/quotations", response_model=list[Quotation])
async def list_quotations(
    request_id: str,
    user: DemoUser = Depends(require_role("procurement")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> list[Quotation]:
    """Liệt kê bản trích xuất của các báo giá thuộc một PR."""
    del user
    if pr_repository.get(request_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")
    return quotation_repository.list_for_pr(request_id)


@router.get("/quotations/{quotation_id}", response_model=Quotation)
async def get_quotation(
    quotation_id: str,
    user: DemoUser = Depends(require_role("procurement")),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> Quotation:
    """Lấy bản trích xuất để người dùng kiểm tra và sửa."""
    quotation = quotation_repository.get(quotation_id)
    if quotation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy báo giá.")
    return quotation


@router.get("/quotations/{quotation_id}/source")
async def download_quotation_source(
    quotation_id: str,
    user: DemoUser = Depends(require_role("procurement")),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> Response:
    """Cho phép nhân viên đối chiếu dữ liệu với file gốc của PR."""
    del user
    quotation = quotation_repository.get(quotation_id)
    if quotation is None or not quotation_repository.source_exists(quotation):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file gốc.")
    return Response(
        content=quotation_repository.read_source(quotation),
        media_type=quotation.source_content_type,
        headers={"Content-Disposition": f'attachment; filename="{quotation.source_filename}"'},
    )


@router.get("/quotations/{quotation_id}/review-preview")
async def get_quotation_review_preview(
    quotation_id: str,
    user: DemoUser = Depends(require_role("procurement")),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> dict:
    """Provide protected page geometry and source-row locations for visual review."""
    del user
    quotation = quotation_repository.get(quotation_id)
    if quotation is None or not quotation_repository.source_exists(quotation):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file gốc.")
    try:
        with quotation_repository.materialize_source(quotation) as source_path:
            return await run_in_threadpool(build_review_preview, source_path, quotation.items)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except OCRServiceError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@router.get("/quotations/{quotation_id}/review-preview/pages/{page_number}")
async def get_quotation_review_preview_page(
    quotation_id: str,
    page_number: int,
    user: DemoUser = Depends(require_role("procurement")),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> Response:
    """Render one protected PDF page for the in-app visual review surface."""
    del user
    quotation = quotation_repository.get(quotation_id)
    if quotation is None or not quotation_repository.source_exists(quotation):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file gốc.")
    try:
        with quotation_repository.materialize_source(quotation) as source_path:
            image = await run_in_threadpool(render_review_preview_page, source_path, page_number)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except OCRServiceError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    return Response(content=image, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.post("/quotations/{quotation_id}/re-extract", response_model=Quotation)
async def reextract_quotation(
    quotation_id: str,
    http_request: Request,
    user: DemoUser = Depends(require_role("procurement")),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> Quotation:
    """Run the configured extraction again for an unconfirmed, previously uploaded file."""
    quotation = quotation_repository.get(quotation_id)
    if quotation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy báo giá.")
    if quotation.status.value == "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Báo giá đã xác nhận không thể trích xuất lại."
        )
    if not quotation_repository.source_exists(quotation):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file gốc.")
    with quotation_repository.materialize_source(quotation) as source_path:
        local_quotation = quotation.model_copy(update={"source_path": str(source_path)})
        if quotation.extraction_mode == "agent":
            extracted, raw, ocr_text = await run_in_threadpool(
                extract_for_quotation,
                local_quotation,
                ocr=getattr(http_request.app.state, "intake_ocr", None),
                extractor=getattr(http_request.app.state, "intake_extractor", None),
            )
            return quotation_repository.apply_agent_extraction(quotation_id, extracted, raw, ocr_text)
        try:
            extracted = extract_quotation(source_path.read_bytes(), source_path.suffix.lower())
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        except OCRServiceError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    refreshed = quotation_repository.replace_extraction(quotation_id, extracted, EXTRACTION_VERSION)
    if refreshed is None:  # pragma: no cover - guarded by lookup above
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy báo giá.")
    return refreshed


@router.post("/quotations/{quotation_id}/reopen", response_model=Quotation)
def reopen_quotation(
    quotation_id: str,
    user: DemoUser = Depends(require_role("procurement")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> Quotation:
    quote = quotation_repository.get(quotation_id)
    if quote is None:
        raise HTTPException(404, "Không tìm thấy báo giá.")
    pr = pr_repository.get(quote.pr_id)
    if pr is None or pr.status not in {PRStatus.COMPARING, PRStatus.AWAITING_QUOTATION}:
        raise HTTPException(409, "Chỉ sửa báo giá trước khi gửi duyệt hoặc sau khi được yêu cầu làm lại.")
    return quotation_repository.reopen(quotation_id)


@router.delete("/quotations/{quotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quotation(
    quotation_id: str,
    user: DemoUser = Depends(require_role("procurement")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> Response:
    """Permanently remove one uploaded quotation before approval."""
    del user
    quotation = quotation_repository.get(quotation_id)
    if quotation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy báo giá.")
    request = pr_repository.get(quotation.pr_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")
    if request.status not in {PRStatus.AWAITING_QUOTATION, PRStatus.COMPARING}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Không thể xóa báo giá sau khi đã gửi duyệt.")

    quotation_repository.delete(quotation_id)
    pr_repository.set_quotation_count(
        quotation.pr_id,
        sum(q.status == QuotationStatus.CONFIRMED for q in quotation_repository.list_for_pr(quotation.pr_id)),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/quotations/{quotation_id}/confirm", response_model=Quotation)
async def confirm_quotation(
    quotation_id: str,
    payload: BuyerQuotationConfirmation,
    user: DemoUser = Depends(require_role("procurement")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> Quotation:
    """Lưu dữ liệu đã sửa và mới cho phép báo giá tham gia bước so sánh."""
    quotation = quotation_repository.get(quotation_id)
    if quotation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy báo giá.")
    request = pr_repository.get(quotation.pr_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")
    if request.status not in {PRStatus.AWAITING_QUOTATION, PRStatus.COMPARING}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PR hiện không thể xác nhận báo giá.")
    try:
        confirmed = quotation_repository.confirm(quotation_id, payload, actor_id=user.id)
        if confirmed is None:  # pragma: no cover - guarded by lookup above
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy báo giá.")
        # Count the current confirmed set, including reopened/reconfirmed quotes only once.
        pr_repository.set_quotation_count(
            quotation.pr_id,
            sum(q.status == QuotationStatus.CONFIRMED for q in quotation_repository.list_for_pr(quotation.pr_id)),
        )
        return confirmed
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except OCRServiceError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


def _fuzzy_quote_item_id(quotation_id: str, item_index: int) -> str:
    """Return the stable line identity shared by the match API and the UI."""
    return f"{quotation_id}:item:{item_index}"


def _fuzzy_pr_item_id(request_id: str, item_id: str | None, item_index: int) -> str:
    """Keep legacy PR rows addressable until every row has a persisted ID."""
    return item_id or f"{request_id}:item:{item_index}"


@router.get("/prs/{request_id}/fuzzy-matches", response_model=BatchMatchResult)
async def get_fuzzy_matches(
    request_id: str,
    user: DemoUser = Depends(require_role("procurement")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> BatchMatchResult:
    """Suggest PR matches while the Buyer reviews extracted quotation lines."""
    del user
    request = pr_repository.get(request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")

    pr_items = [
        FuzzyPRItem(
            id=_fuzzy_pr_item_id(request.id, item.item_id, item.order_index),
            name=item.product_name,
            uom=item.unit,
            description=item.notes,
        )
        for item in request.items
    ]
    # PRs created before structured line items used their category as the
    # single requirement. Keep those historical records comparable.
    if not pr_items:
        pr_items = [
            FuzzyPRItem(
                id=f"{request.id}:main",
                name=request.category,
                uom=request.requested_uom,
            )
        ]

    quote_items = [
        QuoteItemInput(
            id=_fuzzy_quote_item_id(quotation.id, item_index),
            name=item.product_name,
            uom=item.unit,
        )
        for quotation in quotation_repository.list_for_pr(request_id)
        for item_index, item in enumerate(quotation.items)
    ]
    if not quote_items:
        return BatchMatchResult(total=0, auto_matched=0, suggested=0, unmatched=0)
    batch = ProductMatchingService().match(quote_items, pr_items)
    quotes_by_id = {quote.id: quote for quote in quotation_repository.list_for_pr(request_id)}
    pr_by_id = {item.id: item for item in pr_items}
    results = []
    for result in batch.results:
        quote_id, _, raw_index = result.quote_item_id.rpartition(":item:")
        try:
            index = int(raw_index)
        except ValueError:
            results.append(result)
            continue
        quote = quotes_by_id.get(quote_id)
        if quote is None or index >= len(quote.items):
            results.append(result)
            continue
        line = quote.items[index]
        if line.match_status == MatchStatus.REJECTED:
            results.append(result.model_copy(update={"best_match": None, "status": MatchStatus.REJECTED}))
        elif line.match_status == MatchStatus.MANUAL_MATCHED and line.matched_pr_item_id in pr_by_id:
            target = pr_by_id[line.matched_pr_item_id]
            candidate = (
                result.best_match.model_copy(
                    update={"pr_item_id": target.id, "pr_item_name": target.name, "status": MatchStatus.MANUAL_MATCHED}
                )
                if result.best_match
                else None
            )
            if candidate is None:
                candidate = MatchCandidate(
                    pr_item_id=target.id, pr_item_name=target.name, score=1, name_score=1,
                    uom_score=1, attr_score=1, status=MatchStatus.MANUAL_MATCHED,
                )
            results.append(result.model_copy(update={"best_match": candidate, "status": MatchStatus.MANUAL_MATCHED}))
        else:
            results.append(
                result.model_copy(
                    update={"status": result.best_match.status if result.best_match else MatchStatus.UNMATCHED}
                )
            )
    return batch.model_copy(
        update={
            "results": results,
            "auto_matched": sum(result.status == MatchStatus.AUTO_MATCHED for result in results),
            "suggested": sum(result.status == MatchStatus.SUGGESTED for result in results),
            "unmatched": sum(result.status in {MatchStatus.UNMATCHED, MatchStatus.REJECTED} for result in results),
        }
    )


@router.post("/quotations/{quotation_id}/items/{item_id}/confirm-match")
async def confirm_fuzzy_match(
    quotation_id: str,
    item_id: str,
    payload: ConfirmMatchRequest,
    user: DemoUser = Depends(require_role("procurement")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> dict:
    """Xác nhận, từ chối hoặc map thành sản phẩm mới từ kết quả fuzzy match (Đề xuất gộp)."""
    quotation = quotation_repository.get(quotation_id)
    if quotation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy báo giá.")
    request = pr_repository.get(quotation.pr_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")
    if request.status in {PRStatus.PENDING_APPROVAL, PRStatus.APPROVED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PR đang khóa chỉnh sửa.")
    prefix = f"{quotation_id}:item:"
    if not item_id.startswith(prefix) or not item_id[len(prefix):].isdigit():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mã dòng báo giá không hợp lệ.")
    item_index = int(item_id[len(prefix):])
    mapped_id = payload.pr_item_id
    match_status = MatchStatus.REJECTED if payload.action == MatchAction.REJECT else MatchStatus.MANUAL_MATCHED
    if payload.action != MatchAction.REJECT:
        valid_ids = {
            _fuzzy_pr_item_id(request.id, item.item_id, item.order_index) for item in request.items
        } or {f"{request.id}:main"}
        if mapped_id not in valid_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mặt hàng PR đích không hợp lệ.")
    try:
        updated = quotation_repository.set_item_match(
            quotation_id, item_index, pr_item_id=mapped_id if payload.action != MatchAction.REJECT else None,
            match_status=match_status,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy báo giá.")
    return {
        "status": match_status,
        "quotation_id": quotation_id,
        "item_id": item_id,
        "action": payload.action,
        "mapped_pr_item_id": mapped_id if payload.action != MatchAction.REJECT else None,
        "message": "Đã lưu kết quả ghép mặt hàng.",
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Chat with the AI agent."""
    try:
        result = await agent.ainvoke({"query": request.message})
        return ChatResponse(response=result.get("response", ""))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/status")
async def agent_status() -> dict[str, str]:
    """Return the current agent status."""
    return {"status": "ready", "agent": "LangGraph Agent v1.0"}
