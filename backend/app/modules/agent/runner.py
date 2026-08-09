"""Bounded in-process fan-out for independent Agent work items."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Literal


class BatchLimitExceededError(ValueError):
    def __init__(self, requested: int, maximum: int) -> None:
        self.requested = requested
        self.maximum = maximum
        super().__init__(
            f"请求包含 {requested} 个对象，本次最多处理 {maximum} 个；请缩小处理范围。"
        )


def enforce_batch_limit(requested: int, *, maximum: int) -> None:
    if requested > maximum:
        raise BatchLimitExceededError(requested, maximum)


@dataclass(frozen=True, slots=True)
class WorkItem:
    key: str
    input_scope: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WorkResult:
    key: str
    input_scope: dict[str, Any]
    status: Literal["success", "failed"]
    value: Any = None
    error: str | None = None
    attempts: int = 1
    error_code: str | None = None
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class BatchOutcome:
    status: Literal["success", "partial_success", "failed"]
    results: list[WorkResult]

    @property
    def succeeded(self) -> list[WorkResult]:
        return [result for result in self.results if result.status == "success"]

    @property
    def failed(self) -> list[WorkResult]:
        return [result for result in self.results if result.status == "failed"]


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    try:
        from app.services.llm.base import LLMError

        return isinstance(exc, LLMError) and exc.retryable
    except ImportError:  # pragma: no cover - application dependency is always present
        return False


def _run_one(
    item: WorkItem,
    handler: Callable[[WorkItem], Any],
    *,
    retry_once: bool,
) -> WorkResult:
    attempts = 0
    while True:
        attempts += 1
        try:
            return WorkResult(
                key=item.key,
                input_scope=item.input_scope,
                status="success",
                value=handler(item),
                attempts=attempts,
            )
        except Exception as exc:  # failures are isolated to this work item
            retryable = _is_retryable(exc)
            if retry_once and attempts == 1 and retryable:
                continue
            error_code = getattr(exc, "code", None) or type(exc).__name__
            return WorkResult(
                key=item.key,
                input_scope=item.input_scope,
                status="failed",
                error=str(exc) or type(exc).__name__,
                attempts=attempts,
                error_code=str(error_code),
                retryable=retryable,
            )


def run_bounded(
    items: Sequence[WorkItem],
    handler: Callable[[WorkItem], Any],
    *,
    max_concurrency: int,
    retry_once: bool = True,
) -> BatchOutcome:
    """Execute independent I/O-bound work with bounded threads and stable ordering."""
    if not 1 <= max_concurrency <= 8:
        raise ValueError("max_concurrency must be between 1 and 8")
    if not items:
        return BatchOutcome(status="success", results=[])

    indexed: dict[Future[WorkResult], int] = {}
    ordered: list[WorkResult | None] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=min(max_concurrency, len(items))) as pool:
        for index, item in enumerate(items):
            future = pool.submit(_run_one, item, handler, retry_once=retry_once)
            indexed[future] = index
        for future in as_completed(indexed):
            ordered[indexed[future]] = future.result()

    results = [result for result in ordered if result is not None]
    success_count = sum(result.status == "success" for result in results)
    status: Literal["success", "partial_success", "failed"]
    if success_count == len(results):
        status = "success"
    elif success_count:
        status = "partial_success"
    else:
        status = "failed"
    return BatchOutcome(status=status, results=results)


def run_configured(
    items: Sequence[WorkItem],
    handler: Callable[[WorkItem], Any],
    *,
    retry_once: bool = True,
) -> BatchOutcome:
    """Apply deployment-configured batch and concurrency limits."""
    from app.core.config import get_settings

    settings = get_settings()
    enforce_batch_limit(len(items), maximum=settings.agent_max_batch_objects)
    return run_bounded(
        items,
        handler,
        max_concurrency=settings.agent_max_concurrency,
        retry_once=retry_once,
    )
