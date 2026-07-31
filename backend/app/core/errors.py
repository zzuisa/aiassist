"""RFC 9457 Problem Details and the application error hierarchy.

All API failures surface as ``application/problem+json`` with a stable ``code``
and the request ``trace_id``. Domain code raises ``AppError`` subclasses; the
FastAPI exception handlers translate them.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.observability import get_logger, get_trace_id

PROBLEM_CONTENT_TYPE = "application/problem+json"
log = get_logger("api.error")


class AppError(Exception):
    """Base class for domain errors mapped to Problem Details."""

    status: int = 400
    code: str = "bad_request"
    title: str = "Bad Request"

    def __init__(
        self,
        detail: str | None = None,
        *,
        errors: list[dict[str, Any]] | None = None,
        extensions: dict[str, Any] | None = None,
        log_context: dict[str, Any] | None = None,
        code: str | None = None,
        title: str | None = None,
        status: int | None = None,
    ) -> None:
        self.detail = detail
        self.errors = errors
        # Extensions are deliberate, safe Problem Details fields.  They are
        # never populated from request bodies and let clients recover from a
        # state race without parsing a human-readable detail string.
        self.extensions = extensions or {}
        # Logging context is similarly explicit: domain code may add stable
        # identifiers and outcomes, but not arbitrary request data.
        self.log_context = log_context or {}
        if code:
            self.code = code
        if title:
            self.title = title
        if status:
            self.status = status
        super().__init__(detail or self.title)


class NotFoundError(AppError):
    status = 404
    code = "not_found"
    title = "Not Found"


class AuthenticationError(AppError):
    status = 401
    code = "authentication_required"
    title = "Authentication Required"


class PermissionError(AppError):
    status = 403
    code = "forbidden"
    title = "Forbidden"


class ValidationError(AppError):
    status = 422
    code = "validation_error"
    title = "Unprocessable Entity"


class ConflictError(AppError):
    status = 409
    code = "conflict"
    title = "Conflict"


class VersionConflictError(ConflictError):
    code = "version_conflict"
    title = "Version Conflict"


class RateLimitedError(AppError):
    status = 429
    code = "rate_limited"
    title = "Too Many Requests"


class DependencyDegradedError(AppError):
    status = 503
    code = "dependency_unavailable"
    title = "Service Dependency Unavailable"


def problem_response(
    status: int,
    code: str,
    title: str,
    *,
    detail: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    extensions: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"about:blank#{code}",
        "title": title,
        "status": status,
        "code": code,
        "trace_id": trace_id or get_trace_id() or "",
    }
    if detail:
        body["detail"] = detail
    if errors:
        body["errors"] = errors
    if extensions:
        body.update(extensions)
    return JSONResponse(
        status_code=status,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers={"X-Trace-Id": body["trace_id"]},
    )


def register_exception_handlers(app: FastAPI) -> None:
    def _request_fields(request: Request) -> dict[str, str]:
        return {"method": request.method, "path": request.url.path}

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        logger = log.error if exc.status >= 500 else log.warning
        logger(
            exc.log_context.get("event", "api_request_failed"),
            # Keep the event stable for aggregations but make Kibana's
            # default message column explain what actually happened.
            message=exc.detail or exc.title,
            status_code=exc.status,
            error_code=exc.code,
            error_type=type(exc).__name__,
            **_request_fields(request),
            **{key: value for key, value in exc.log_context.items() if key != "event"},
        )
        return problem_response(
            exc.status,
            exc.code,
            exc.title,
            detail=exc.detail,
            errors=exc.errors,
            extensions=exc.extensions,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        log.warning(
            "api_request_validation_failed",
            status_code=422,
            error_code="validation_error",
            error_type=type(exc).__name__,
            error_count=len(errors),
            error_locations=[".".join(str(part) for part in item["loc"]) for item in errors[:20]],
            **_request_fields(request),
        )
        return problem_response(422, "validation_error", "Unprocessable Entity", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "authentication_required", 403: "forbidden", 404: "not_found"}.get(
            exc.status_code, "http_error"
        )
        logger = log.error if exc.status_code >= 500 else log.warning
        logger(
            "api_http_error",
            status_code=exc.status_code,
            error_code=code,
            error_type=type(exc).__name__,
            **_request_fields(request),
        )
        return problem_response(exc.status_code, code, str(exc.detail or "HTTP Error"))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception(
            "api_unhandled_exception",
            status_code=500,
            error_code="internal_error",
            error_type=type(exc).__name__,
            **_request_fields(request),
        )
        return problem_response(500, "internal_error", "Internal Server Error")
