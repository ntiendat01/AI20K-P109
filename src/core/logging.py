import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

STRUCTURED_LOG_FIELDS = (
    "http_method",
    "http_path",
    "status_code",
    "duration_ms",
    "event",
    "error_type",
    "error_count",
    "actor_id",
    "actor_role",
    "required_roles",
    "resource",
    "resource_id",
    "previous_status",
    "new_status",
    "storage_backend",
    "file_name",
)


def bind_request_id(request_id: str) -> Token[str]:
    """Attach a request ID to every log record emitted by the current task."""
    return _request_id.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    """Restore the request context after an HTTP request has completed."""
    _request_id.reset(token)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    """Emit one machine-readable JSON object per line for production log collectors."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for field in STRUCTURED_LOG_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    """Configure application logs for stdout-based production collection."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[handler],
        force=True,
    )

    # These libraries are useful at warning level but too noisy for request debugging.
    for logger_name in ("httpcore", "httpx"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
