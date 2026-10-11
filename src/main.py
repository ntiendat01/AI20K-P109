import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import router
from src.api.routes.evaluation import router as evaluation_router
from src.api.routes.pr import router as pr_router
from src.api.routes.procurement_workflow import initialize_procurement
from src.api.routes.procurement_workflow import router as procurement_router
from src.core.config import get_settings
from src.core.logging import bind_request_id, configure_logging, reset_request_id
from src.services.auth import get_session
from src.services.procurement.purchase_orders import get_po_repository
from src.services.procurement.purchase_requests import get_pr_repository
from src.services.quotation.repository import get_quotation_repository

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting: name=%s env=%s", settings.app_name, settings.app_env)
    service = initialize_procurement(app)
    service.reconcile(get_pr_repository(), get_quotation_repository(), get_po_repository())
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(pr_router, prefix="/api")
app.include_router(evaluation_router, prefix="/api")
app.include_router(procurement_router, prefix="/api/v1")

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/ui", StaticFiles(directory=frontend_dir, html=True), name="frontend")


@app.exception_handler(RequestValidationError)
async def log_request_validation_error(request: Request, error: RequestValidationError):
    logger.warning(
        "HTTP request validation failed",
        extra={
            "event": "http_validation_failed",
            "http_method": request.method,
            "http_path": request.url.path,
            "status_code": 422,
            "error_type": type(error).__name__,
            "error_count": len(error.errors()),
        },
    )
    return await request_validation_exception_handler(request, error)


@app.exception_handler(HTTPException)
async def log_http_exception(request: Request, error: HTTPException):
    logger.warning(
        "HTTP exception handled",
        extra={
            "event": "http_exception_handled",
            "http_method": request.method,
            "http_path": request.url.path,
            "status_code": error.status_code,
            "error_type": type(error).__name__,
        },
    )
    return await http_exception_handler(request, error)


@app.middleware("http")
async def authenticated_evaluation_actor(request, call_next):
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        try:
            user = get_session(header.removeprefix("Bearer ")).user
            service = getattr(request.app.state, "procurement_workflow", None)
            if service is not None:
                request.state.actor = service.actor(user, [pr.id for pr in get_pr_repository().list()])
        except HTTPException:
            pass  # Normal route dependencies return the authentication error.
    return await call_next(request)


@app.middleware("http")
async def disable_development_ui_cache(request, call_next):
    """Ensure a browser never reuses an old CSS/JS file during local UI work."""
    response = await call_next(request)
    if settings.app_env == "development" and request.url.path.startswith("/ui/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.middleware("http")
async def log_http_request(request, call_next):
    """Log request outcomes without recording query strings, headers, or bodies."""
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_request_id if REQUEST_ID_PATTERN.fullmatch(supplied_request_id) else uuid4().hex
    token = bind_request_id(request_id)
    started_at = time.perf_counter()

    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started_at) * 1000
        log = logger.warning if response.status_code >= 500 else logger.info
        log(
            "HTTP request completed",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.exception(
            "HTTP request failed",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "duration_ms": round(duration_ms, 2),
            },
        )
        raise
    finally:
        reset_request_id(token)


@app.get("/", include_in_schema=False)
async def frontend():
    return RedirectResponse(url="/ui/")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
