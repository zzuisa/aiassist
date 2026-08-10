"""Desensitized execution-record persistence."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.agent import ExecutionRecord

_SENSITIVE_KEY = re.compile(
    r"(?:password|token|secret|api[_-]?key|cookie|authorization|private[_-]?key)",
    re.IGNORECASE,
)
_REDACTED = "[redacted]"


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, (uuid.UUID, date, datetime)):
        return value.isoformat() if not isinstance(value, uuid.UUID) else str(value)
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def redact_sensitive(value: Any, *, key: str | None = None) -> Any:
    """Recursively redact secret-like keys and credential-shaped values."""
    if key is not None and _SENSITIVE_KEY.search(key):
        return _REDACTED
    if isinstance(value, Mapping):
        return {str(k): redact_sensitive(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str) and (value.startswith("eyJ") or value.lower().startswith("bearer ")):
        return _REDACTED
    return _safe_scalar(value)


def write_execution_record(
    session: Session,
    *,
    task_id: uuid.UUID,
    step_id: str | None = None,
    agent_name: str,
    step_label: str,
    tool_name: str,
    operation_type: str,
    params: Mapping[str, Any],
    status: str,
    run_id: uuid.UUID | None = None,
    result_summary: str | None = None,
    error_reason: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> ExecutionRecord:
    """Write one record after redaction; caller owns the surrounding transaction."""
    started = started_at or datetime.now(UTC)
    finished = finished_at or datetime.now(UTC)
    duration_ms = max(0, int((finished - started).total_seconds() * 1000))
    if step_id is None:
        count = session.scalar(
            select(func.count(ExecutionRecord.id)).where(ExecutionRecord.task_id == task_id)
        )
        step_id = f"step-{int(count or 0) + 1:04d}"
    record = ExecutionRecord(
        task_id=task_id,
        run_id=run_id,
        step_id=step_id,
        agent_name=agent_name,
        step_label=step_label,
        tool_name=tool_name,
        operation_type=operation_type,
        params_digest_json=redact_sensitive(params),
        result_summary=result_summary,
        status=status,
        error_reason=error_reason,
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
    )
    session.add(record)
    session.flush()
    return record


def list_execution_records(
    session: Session,
    task_id: uuid.UUID,
) -> list[ExecutionRecord]:
    """Return one task's durable audit trail in insertion/execution order."""
    return list(
        session.scalars(
            select(ExecutionRecord)
            .where(ExecutionRecord.task_id == task_id)
            .order_by(ExecutionRecord.id.asc())
        ).all()
    )
