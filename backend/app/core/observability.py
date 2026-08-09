"""W3C trace-context propagation and safe structured logging.

A per-request trace ID is stored in a context variable and echoed on responses,
outbox events, messages, jobs and logs. Logs never contain secrets, tokens,
signed URLs, raw prompts or media bytes.
"""

from __future__ import annotations

import hashlib
import logging
import logging.handlers
import os
import re
import secrets
import threading
from collections import Counter
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
_PRIVATE_CONTENT_FIELDS = frozenset(
    {
        "body",
        "candidate",
        "content",
        "diagnostic",
        "markdown",
        "media",
        "normalized_markdown",
        "original_text",
        "payload",
        "prompt",
        "raw_content",
        "request",
        "request_body",
        "response",
        "response_body",
        "result",
        "system_prompt",
        "transcript",
        "user_payload",
    }
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_QUERY_RE = re.compile(r"(?i)([?&](?:token|secret|api[_-]?key|signature)=)[^&\s]+")
_API_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
_METRIC_NAME_RE = re.compile(r"^[a-z][a-z0-9_.]{0,95}$")
_metrics_lock = threading.Lock()
_metrics: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()


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


def _safe_string(value: str) -> str:
    value = _BEARER_RE.sub("Bearer [redacted]", value)
    value = _SECRET_QUERY_RE.sub(r"\1[redacted]", value)
    return _API_KEY_RE.sub("[redacted]", value)


def _redact_value(value: Any) -> Any:
    if isinstance(value, MutableMapping):
        cleaned: dict[str, Any] = {}
        for key, nested in value.items():
            normalized = str(key).lower()
            if _SENSITIVE.search(normalized) or normalized in _PRIVATE_CONTENT_FIELDS:
                cleaned[str(key)] = "[redacted]"
            else:
                cleaned[str(key)] = _redact_value(nested)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _safe_string(value)
    return value


def record_metric(name: str, value: int = 1, **labels: str) -> None:
    """Record a bounded in-process operational counter.

    Labels are intentionally limited to low-cardinality dimensions. Entity IDs
    belong in correlated logs, never metric labels.
    """
    if not _METRIC_NAME_RE.fullmatch(name) or value < 0:
        raise ValueError("invalid metric")
    allowed = {"event", "operation", "outcome", "error_code", "job_type"}
    safe_labels = tuple(
        sorted(
            (key, _safe_string(str(label))[:80])
            for key, label in labels.items()
            if key in allowed and label is not None
        )
    )
    with _metrics_lock:
        _metrics[(name, safe_labels)] += value


def metrics_snapshot() -> list[dict[str, Any]]:
    with _metrics_lock:
        return [
            {"name": name, "labels": dict(labels), "value": value}
            for (name, labels), value in sorted(_metrics.items())
        ]


def reset_metrics() -> None:
    with _metrics_lock:
        _metrics.clear()


def safe_blog_context(
    *,
    job_id: Any | None = None,
    post_id: Any | None = None,
    source_id: Any | None = None,
    skill_version_id: Any | None = None,
    content: str | None = None,
    validation_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Build correlated diagnostics from identifiers and content metadata only."""
    context: dict[str, Any] = {
        key: str(value)
        for key, value in {
            "job_id": job_id,
            "post_id": post_id,
            "source_id": source_id,
            "skill_version_id": skill_version_id,
        }.items()
        if value is not None
    }
    if content is not None:
        context["content_chars"] = len(content)
        context["content_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if validation_codes is not None:
        context["validation_codes"] = [str(code)[:64] for code in validation_codes[:20]]
    return context


def _redact_processor(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict.keys()):
        normalized = str(key).lower()
        if _SENSITIVE.search(normalized) or normalized in _PRIVATE_CONTENT_FIELDS:
            event_dict[key] = "[redacted]"
        else:
            event_dict[key] = _redact_value(event_dict[key])
    tid = get_trace_id()
    if tid:
        event_dict.setdefault("trace_id", tid)
    return event_dict


def _capture_blog_metric(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    event = str(event_dict.get("event", ""))
    if event.startswith(("blog_", "blog.")):
        outcome = event_dict.get("outcome")
        error_code = event_dict.get("error_code") or event_dict.get("code")
        if outcome is not None and error_code is not None:
            record_metric(
                "blog.events_total",
                event=event,
                outcome=str(outcome),
                error_code=str(error_code),
            )
        elif outcome is not None:
            record_metric("blog.events_total", event=event, outcome=str(outcome))
        elif error_code is not None:
            record_metric("blog.events_total", event=event, error_code=str(error_code))
        else:
            record_metric("blog.events_total", event=event)
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
    for logger in named_loggers:
        # Celery may disable pre-existing stdlib loggers while installing its
        # own logging configuration. Re-enable the application-owned targets
        # whenever our idempotent setup runs after Celery's signal.
        logger.disabled = False
        logger.setLevel(numeric_level)
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
            _capture_blog_metric,
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
    # Celery's logging bootstrap may disable stdlib loggers that were created
    # earlier during module import. Application loggers must recover whenever
    # they are requested so later API/worker events still reach the managed
    # root handlers (and test capture handlers).
    stdlib_logger = logging.getLogger(name)
    stdlib_logger.disabled = False
    if not name.startswith(("uvicorn", "celery")):
        stdlib_logger.propagate = True
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
