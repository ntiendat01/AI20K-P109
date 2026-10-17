"""HTTP boundary for the isolated OCR service."""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

import pymupdf as fitz
from fastapi import FastAPI, File, Form, Header, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from ocr.ocr_service.engine import OCREngine, PaddleOCREngine, RapidOCREngine, get_engine_class
from ocr.ocr_service import pdf_ops
from ocr.ocr_service.settings import OCRServiceSettings
from src.infrastructure.ocr.contracts import OCRErrorCode, OCRErrorResponse, OCRResponse, PDFExtractResponse

logger = logging.getLogger(__name__)
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8\xff"


def create_app(
    *,
    settings: OCRServiceSettings | None = None,
    engine_factory: type[OCREngine] | None = None,
) -> FastAPI:
    """Create the OCR service app with injectable settings and engine for tests."""
    resolved_settings = settings or OCRServiceSettings()
    resolved_engine_factory = engine_factory or get_engine_class(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = resolved_engine_factory(resolved_settings)
        app.state.ready = False
        try:
            await run_in_threadpool(app.state.engine.warm_up)
        except Exception:
            logger.exception("OCR service warm-up failed")
        else:
            app.state.ready = True
        yield

    app = FastAPI(title="Procura OCR Service", version="1.0.0", lifespan=lifespan)

    @app.get("/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/ready")
    async def ready():
        if app.state.ready:
            return {"status": "ready"}
        return _error_response(
            request_id="readiness",
            code=OCRErrorCode.SERVICE_UNAVAILABLE,
            detail="OCR model is not ready.",
            retryable=True,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @app.post(
        "/v1/ocr",
        response_model=OCRResponse,
        responses={
            400: {"model": OCRErrorResponse},
            401: {"model": OCRErrorResponse},
            413: {"model": OCRErrorResponse},
            422: {"model": OCRErrorResponse},
            429: {"model": OCRErrorResponse},
            503: {"model": OCRErrorResponse},
        },
    )
    async def extract(
        document: UploadFile = File(...),
        x_ocr_service_token: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
    ):
        request_id = x_request_id or str(uuid4())
        if resolved_settings.ocr_service_token and x_ocr_service_token != resolved_settings.ocr_service_token:
            return _error_response(
                request_id=request_id,
                code=OCRErrorCode.INVALID_DOCUMENT,
                detail="OCR service authentication failed.",
                retryable=False,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        if not app.state.ready:
            return _error_response(
                request_id=request_id,
                code=OCRErrorCode.SERVICE_UNAVAILABLE,
                detail="OCR model is not ready.",
                retryable=True,
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        document_bytes = await _read_limited(document, resolved_settings.ocr_max_upload_bytes)
        if document_bytes is None:
            return _error_response(
                request_id=request_id,
                code=OCRErrorCode.PAYLOAD_TOO_LARGE,
                detail="Document exceeds the configured size limit.",
                retryable=False,
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
        suffix = _document_suffix(document_bytes, document.filename)
        if suffix is None:
            return _error_response(
                request_id=request_id,
                code=OCRErrorCode.INVALID_DOCUMENT,
                detail="Only PDF, PNG, and JPEG documents are supported.",
                retryable=False,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        page_count = _page_count(document_bytes, suffix)
        if page_count is None:
            return _error_response(
                request_id=request_id,
                code=OCRErrorCode.INVALID_DOCUMENT,
                detail="Document cannot be decoded.",
                retryable=False,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if page_count > resolved_settings.ocr_max_pages:
            return _error_response(
                request_id=request_id,
                code=OCRErrorCode.TOO_MANY_PAGES,
                detail="Document exceeds the configured page limit.",
                retryable=False,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            pages = await run_in_threadpool(app.state.engine.extract, document_bytes, suffix)
        except Exception:
            logger.exception("OCR extraction failed", extra={"request_id": request_id})
            return _error_response(
                request_id=request_id,
                code=OCRErrorCode.PROCESSING_FAILED,
                detail="OCR processing failed.",
                retryable=True,
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return OCRResponse(
            request_id=request_id,
            document_sha256=hashlib.sha256(document_bytes).hexdigest(),
            engine="rapidocr" if isinstance(app.state.engine, RapidOCREngine) else "paddleocr",
            model_version=resolved_settings.ocr_model_version,
            pages=pages,
        )

    async def pdf_document(document: UploadFile, token: str | None, request_id: str):
        if resolved_settings.ocr_service_token and token != resolved_settings.ocr_service_token:
            return None, _error_response(
                request_id=request_id, code=OCRErrorCode.INVALID_DOCUMENT,
                detail="OCR service authentication failed.", retryable=False,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        content = await _read_limited(document, resolved_settings.ocr_max_upload_bytes)
        if content is None:
            return None, _error_response(
                request_id=request_id, code=OCRErrorCode.PAYLOAD_TOO_LARGE,
                detail="Document exceeds the configured size limit.", retryable=False,
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
        if not content.startswith(b"%PDF-"):
            return None, _error_response(
                request_id=request_id, code=OCRErrorCode.INVALID_DOCUMENT,
                detail="Only PDF documents are supported.", retryable=False,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        pages = _page_count(content, ".pdf")
        if not pages:
            return None, _error_response(
                request_id=request_id, code=OCRErrorCode.INVALID_DOCUMENT,
                detail="PDF không hợp lệ hoặc bị hỏng.", retryable=False,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if pages > resolved_settings.ocr_max_pages:
            return None, _error_response(
                request_id=request_id, code=OCRErrorCode.TOO_MANY_PAGES,
                detail=f"PDF vượt quá giới hạn {resolved_settings.ocr_max_pages} trang.", retryable=False,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return content, None

    @app.post("/v1/pdf/extract", response_model=PDFExtractResponse)
    async def extract_pdf(
        document: UploadFile = File(...),
        x_ocr_service_token: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
    ):
        request_id = x_request_id or str(uuid4())
        content, error = await pdf_document(document, x_ocr_service_token, request_id)
        if error:
            return error
        if not app.state.ready:
            return _error_response(
                request_id=request_id, code=OCRErrorCode.SERVICE_UNAVAILABLE,
                detail="OCR model is not ready.", retryable=True,
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            return await run_in_threadpool(pdf_ops.extract_pdf, content, app.state.engine)
        except ValueError as exc:
            return _pdf_error(request_id, str(exc))
        except Exception:
            logger.exception("PDF extraction failed", extra={"request_id": request_id})
            return _error_response(
                request_id=request_id, code=OCRErrorCode.PROCESSING_FAILED,
                detail="PDF extraction failed.", retryable=True,
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @app.post("/v1/pdf/type")
    async def pdf_type(
        document: UploadFile = File(...),
        x_ocr_service_token: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
    ):
        request_id = x_request_id or str(uuid4())
        content, error = await pdf_document(document, x_ocr_service_token, request_id)
        if error:
            return error
        try:
            return {"document_type": await run_in_threadpool(pdf_ops.detect_pdf_type, content)}
        except (fitz.FileDataError, fitz.EmptyFileError, ValueError) as exc:
            return _pdf_error(request_id, str(exc))
        except Exception:
            logger.exception("PDF type detection failed", extra={"request_id": request_id})
            return _pdf_processing_error(request_id)

    @app.post("/v1/pdf/native-text")
    async def pdf_native_text(
        document: UploadFile = File(...),
        x_ocr_service_token: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
    ):
        request_id = x_request_id or str(uuid4())
        content, error = await pdf_document(document, x_ocr_service_token, request_id)
        if error:
            return error
        try:
            return {"text": await run_in_threadpool(pdf_ops.native_pdf_text, content)}
        except (fitz.FileDataError, fitz.EmptyFileError, ValueError) as exc:
            return _pdf_error(request_id, str(exc))
        except Exception:
            logger.exception("Native PDF text extraction failed", extra={"request_id": request_id})
            return _pdf_processing_error(request_id)

    @app.post("/v1/pdf/review-preview")
    async def pdf_review_preview(
        document: UploadFile = File(...),
        items_json: str = Form(...),
        x_ocr_service_token: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
    ):
        request_id = x_request_id or str(uuid4())
        content, error = await pdf_document(document, x_ocr_service_token, request_id)
        if error:
            return error
        try:
            items = json.loads(items_json)
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise ValueError("Invalid quotation items")
        except (ValueError, TypeError):
            return _pdf_error(request_id, "Dữ liệu dòng hàng không hợp lệ.")
        try:
            return await run_in_threadpool(pdf_ops.build_review_preview, content, items)
        except (fitz.FileDataError, fitz.EmptyFileError, ValueError) as exc:
            return _pdf_error(request_id, str(exc))
        except Exception:
            logger.exception("PDF review preview failed", extra={"request_id": request_id})
            return _pdf_processing_error(request_id)

    @app.post("/v1/pdf/review-preview/pages/{page_number}")
    async def pdf_review_preview_page(
        page_number: int,
        document: UploadFile = File(...),
        x_ocr_service_token: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
    ):
        request_id = x_request_id or str(uuid4())
        content, error = await pdf_document(document, x_ocr_service_token, request_id)
        if error:
            return error
        try:
            image = await run_in_threadpool(pdf_ops.render_review_preview_page, content, page_number)
        except (fitz.FileDataError, fitz.EmptyFileError, ValueError) as exc:
            return _pdf_error(request_id, str(exc))
        except Exception:
            logger.exception("PDF preview rendering failed", extra={"request_id": request_id})
            return _pdf_processing_error(request_id)
        return Response(content=image, media_type="image/png")

    return app


async def _read_limited(document: UploadFile, max_bytes: int) -> bytes | None:
    chunks: list[bytes] = []
    total_size = 0
    while chunk := await document.read(64 * 1024):
        total_size += len(chunk)
        if total_size > max_bytes:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _document_suffix(document: bytes, filename: str | None) -> str | None:
    del filename
    if document.startswith(b"%PDF-"):
        return ".pdf"
    if document.startswith(_PNG_SIGNATURE):
        return ".png"
    if document.startswith(_JPEG_SIGNATURE):
        return ".jpg"
    return None


def _page_count(document: bytes, suffix: str) -> int | None:
    if suffix != ".pdf":
        return 1
    try:
        with fitz.open(stream=document, filetype="pdf") as pdf:
            return len(pdf)
    except (fitz.EmptyFileError, fitz.FileDataError, RuntimeError, ValueError):
        return None


def _pdf_error(request_id: str, detail: str) -> JSONResponse:
    return _error_response(
        request_id=request_id, code=OCRErrorCode.INVALID_DOCUMENT,
        detail=detail, retryable=False, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


def _pdf_processing_error(request_id: str) -> JSONResponse:
    return _error_response(
        request_id=request_id, code=OCRErrorCode.PROCESSING_FAILED,
        detail="PDF processing failed.", retryable=True,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _error_response(
    *, request_id: str, code: OCRErrorCode, detail: str, retryable: bool, status_code: int
) -> JSONResponse:
    error = OCRErrorResponse(
        request_id=request_id,
        code=code,
        detail=detail,
        retryable=retryable,
    )
    return JSONResponse(status_code=status_code, content=error.model_dump(mode="json"))


app = create_app()
