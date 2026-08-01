"""W3C trace-context propagation and safe structured logging.

A per-request trace ID is stored in a context variable and echoed on responses,
outbox events, messages, jobs and logs. Logs never contain secrets, tokens,
signed URLs, raw prompts or media bytes.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import secrets
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
from structlog.typing import Processor

_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)

# W3C traceparent: version-traceid-parentid-flags
_TRACEPARENT_RE = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$")

# Header/field names we redact if they ever reach the logger.
_SENSITIVE = re.compile(
    r"(password|secret|token|authorization|cookie|signing_key|api[_-]?key)", re.IGNORECASE
)


def new_trace_id() -> str:
    return secrets.token_hex(16)


def get_trace_id() -> str | None:
    return _trace_id.get()


def set_trace_id(value: str | None) -> None:
    _trace_id.set(value)


def extract_trace_id(traceparent: str | None) -> str:
    if traceparent:
        m = _TRACEPARENT_RE.match(traceparent.strip())
        if m:
            return m.group(1)
    return new_trace_id()


def _redact_processor(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict.keys()):
        if _SENSITIVE.search(key):
            event_dict[key] = "[redacted]"
    tid = get_trace_id()
    if tid:
        event_dict.setdefault("trace_id", tid)
    return event_dict


def _ensure_message(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Expose the human-readable log body through the ECS message field.

    Structlog calls this field event. Keeping both preserves the stable
    machine event name while making logs readable in Kibana's message column.
    """
    event = event_dict.get("event")
    if event is not None:
        event_dict.setdefault("message", str(event))
    return event_dict


def configure_logging(level: str = "INFO", service: str = "backend") -> None:
    """Configure one-line JSON logs for structlog and stdlib loggers.

    Uvicorn and Celery install their own non-propagating loggers.  Merely adding
    a handler to the root logger therefore leaves their persistent log files
    empty.  Managed handlers are attached to those loggers explicitly and this
    function is idempotent so Celery's post-setup signals can safely call it.
    """
    numeric_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)

    def add_service(
        _: Any, __: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        event_dict.setdefault("service", service)
        return event_dict

    class ExcludeUvicornAccess(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return record.name != "uvicorn.access"

    foreign_pre_chain: list[Processor] = [
        _redact_processor,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_service,
    ]
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.processors.format_exc_info,
            _ensure_message,
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=foreign_pre_chain,
    )

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # A worker can configure logging once during import and again after Celery
    # has replaced its handlers. Remove only handlers managed by this module.
    named_loggers = [
        logging.getLogger(name)
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "celery.task")
    ]
    closed: set[int] = set()
    for logger in [root, *named_loggers]:
        for handler in list(logger.handlers):
            if getattr(handler, "_aiassist_managed", False):
                logger.removeHandler(handler)
                if id(handler) not in closed:
                    handler.close()
                    closed.add(id(handler))

    # --- stdout handler (always) -------------------------------------------
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler._aiassist_managed = True  # type: ignore[attr-defined]
    root.addHandler(stream_handler)

    # --- file handler (when LOG_DIR is injected by compose) -----------------
    log_dir = os.environ.get("LOG_DIR", "")
    if log_dir:
        log_path = os.path.join(log_dir, f"{service}.log")
        try:
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=10 * 1024 * 1024,  # 10 MiB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler._aiassist_managed = True  # type: ignore[attr-defined]
            if service == "backend":
                # Nginx owns HTTP access logging. Keeping the duplicate
                # Uvicorn access stream out of backend.log makes the business
                # index contain application events and failures only.
                file_handler.addFilter(ExcludeUvicornAccess())
            root.addHandler(file_handler)
            # Uvicorn/Celery loggers commonly set propagate=False. Attach the
            # same file handler only in that case to avoid duplicate records.
            for logger in named_loggers:
                if not logger.propagate:
                    logger.addHandler(file_handler)
        except OSError:
            # Mount may not be ready yet; fall back to stdout-only gracefully.
            pass

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _redact_processor,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            add_service,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str = "aiassist") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


class TraceContextMiddleware(BaseHTTPMiddleware):
    """Assign/propagate a trace ID and set X-Trace-Id on every response."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        tid = extract_trace_id(request.headers.get("traceparent"))
        set_trace_id(tid)
        try:
            response = await call_next(request)
        finally:
            pass
        response.headers["X-Trace-Id"] = tid
        return response
