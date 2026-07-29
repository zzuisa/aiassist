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


def configure_logging(level: str = "INFO", service: str = "backend") -> None:
    """Configure structlog to write JSON to stdout and, when LOG_DIR is set,
    also to a rotating file at ``$LOG_DIR/<service>.log`` (10 MiB × 5 files).
    The file handler is added to the root logger so every stdlib log (SQLAlchemy,
    uvicorn, celery, …) also flows there; structlog uses the same root handler.
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    # --- stdout handler (always) -------------------------------------------
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
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
            file_handler.setFormatter(logging.Formatter("%(message)s"))
            root.addHandler(file_handler)
        except OSError:
            # Mount may not be ready yet; fall back to stdout-only gracefully.
            pass

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _redact_processor,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
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
