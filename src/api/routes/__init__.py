import csv
import hashlib
import io
from pathlib import Path

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
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from src.agents.graph import agent
from src.api.dependencies import get_current_user, require_role
from src.core.config import get_settings
from src.extraction.service import process_pdf
from src.models.extracted_quotation import BatchExtractionResult, ExtractionResult, ExtractionStatus
from src.models.fuzzy_match import BatchMatchResult, ConfirmMatchRequest
from src.models.purchase_request import (
    PRStatus,
    PurchaseRequest,
    PurchaseRequestCreate,
    PurchaseRequestUpdate,
)
from src.models.schemas import (
    ChatRequest,
    ChatResponse,
    LoginRequest,
    LoginResponse,
    PRComparisonResponse,
    PurchaseOrder,
    Quotation,
    QuotationConfirmation,
    QuotationStatus,
    UserProfile,
)
from src.services.auth import DemoUser, authenticate, create_session, revoke_session
from src.services.fuzzy_match import PRItem as FuzzyPRItem
from src.services.fuzzy_match import ProductMatchingService, QuoteItemInput
from src.services.procurement.comparison import build_comparison
from src.services.procurement.purchase_orders import PurchaseOrderRepository, get_po_repository
from src.services.procurement.purchase_requests import PurchaseRequestRepository, get_pr_repository
from src.services.quotation.intake import extract_for_quotation
from src.services.quotation.parser import EXTRACTION_VERSION, ExtractedQuotation, extract_quotation
from src.services.quotation.pdf_review import build_review_preview, render_review_preview_page
from src.services.quotation.repository import QuotationRepository, get_quotation_repository

router = APIRouter()

MAX_QUOTATION_FILE_BYTES = 5 * 1024 * 1024
MAX_QUOTATIONS_PER_PR = 10
MAX_BATCH_EXTRACTION_FILES = 5
SUPPORTED_QUOTATION_SUFFIXES = {".pdf", ".txt", ".eml"}


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
            items.append({
                "product_name": product_name,
                "quantity": quantity_str,
                "unit": unit,
                "notes": notes,
                "order_index": i - 1,
            })

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
    user: DemoUser = Depends(require_role("procurement")),
    pr_repository: PurchaseRequestRepository = Depends(get_pr_repository),
    quotation_repository: QuotationRepository = Depends(get_quotation_repository),
) -> PurchaseRequest:
    """Update a PR only while it has no uploaded supplier quotations."""
    del user
    if pr_repository.get(request_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")
    if quotation_repository.list_for_pr(request_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể chỉnh sửa PR khi vẫn còn báo giá đã tải lên. Hãy xóa hết báo giá trước.",
        )
    updated = pr_repository.update(request_id, payload)
    if updated is None:  # pragma: no cover - guarded by lookup above
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy PR.")
    return updated


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
        extracted, raw, ocr_text = await run_in_threadpool(
            extract_for_quotation,
            saved,
            ocr=getattr(http_request.app.state, "intake_ocr", None),
            extractor=getattr(http_request.app.state, "intake_extractor", None),
        )
        return quotation_repository.apply_agent_extraction(saved.id, extracted, raw, ocr_text)
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
) -> FileResponse:
    """Cho phép nhân viên đối chiếu dữ liệu với file gốc của PR."""
    del user
    quotation = quotation_repository.get(quotation_id)
    if quotation is None or not Path(quotation.source_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file gốc.")
    return FileResponse(
        quotation.source_path,
        media_type=quotation.source_content_type,
        filename=quotation.source_filename,
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
    if quotation is None or not Path(quotation.source_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file gốc.")
    try:
        return build_review_preview(Path(quotation.source_path), quotation.items)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


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
    if quotation is None or not Path(quotation.source_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file gốc.")
    try:
        image = render_review_preview_page(Path(quotation.source_path), page_number)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
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
    source_path = Path(quotation.source_path)
    if not source_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file gốc.")
    if quotation.extraction_mode == "agent":
        extracted, raw, ocr_text = await run_in_threadpool(
            extract_for_quotation,
            quotation,
            ocr=getattr(http_request.app.state, "intake_ocr", None),
            extractor=getattr(http_request.app.state, "intake_extractor", None),
        )
        return quotation_repository.apply_agent_extraction(quotation_id, extracted, raw, ocr_text)
    try:
        extracted = extract_quotation(source_path.read_bytes(), source_path.suffix.lower())
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
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
    payload: QuotationConfirmation,
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
    """Match confirmed quotation lines to the PR names used in comparison."""
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
        if quotation.status == QuotationStatus.CONFIRMED
        for item_index, item in enumerate(quotation.items)
    ]
    if not quote_items:
        return BatchMatchResult(total=0, auto_matched=0, suggested=0, unmatched=0)
    return ProductMatchingService().match(quote_items, pr_items)


@router.post("/quotations/{quotation_id}/items/{item_id}/confirm-match")
async def confirm_fuzzy_match(
    quotation_id: str,
    item_id: str,
    payload: ConfirmMatchRequest,
    user: DemoUser = Depends(require_role("procurement")),
) -> dict:
    """Xác nhận, từ chối hoặc map thành sản phẩm mới từ kết quả fuzzy match (Đề xuất gộp)."""
    # TODO: Persist the confirmed synonym to the SynonymDictionary DB table.
    # In a fully integrated flow, this would also update the quote_item's matched_pr_item_id.

    # Giả lập ghi nhận kết quả match:
    return {
        "status": "success",
        "quotation_id": quotation_id,
        "item_id": item_id,
        "action": payload.action,
        "mapped_pr_item_id": payload.pr_item_id,
        "message": "Đã cập nhật kết quả fuzzy match."
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
