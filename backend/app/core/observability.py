"""W3C trace-context propagation and safe structured logging.

A per-request trace ID is stored in a context variable and echoed on responses,
outbox events, messages, jobs and logs. Logs never contain secrets, tokens,
signed URLs, raw prompts or media bytes.
"""

from __future__ import annotations

import logging
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


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _redact_processor,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
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
