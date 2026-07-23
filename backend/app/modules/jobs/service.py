"""Durable async job state machine and append-only event log.

Every meaningful transition updates ``async_jobs`` and appends an
``async_job_events`` row in the SAME transaction, then publishes a small Redis
wakeup (best-effort). Progress never decreases within an attempt. Celery state is
never the business truth.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.foundation import AsyncJob, AsyncJobEvent

TERMINAL = {"completed", "failed", "cancelled"}

_EVENT_FOR_STATUS = {
    "queued": "job.updated",
    "processing": "job.updated",
    "waiting_user": "job.waiting_user",
    "completed": "job.completed",
    "failed": "job.failed",
    "cancelled": "job.cancelled",
}


def create_job(
    session: Session,
    *,
    user_id: uuid.UUID,
    job_type: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    priority: int = 0,
    max_retries: int = 3,
    trace_id: str | None = None,
) -> AsyncJob:
    """Create (or return existing) job for the idempotency key. No commit."""
    if idempotency_key:
        existing = session.scalar(
            select(AsyncJob).where(
                AsyncJob.user_id == user_id, AsyncJob.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            return existing
    job = AsyncJob(
        id=uuid.uuid4(),
        user_id=user_id,
        job_type=job_type,
        entity_type=entity_type,
        entity_id=entity_id,
        status="pending",
        version=1,
        priority=priority,
        progress=0,
        max_retries=max_retries,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
    )
    session.add(job)
    session.flush()
    _append_event(session, job, "job.updated")
    return job


def _append_event(
    session: Session, job: AsyncJob, event_type: str, extra: dict | None = None
) -> None:
    def _iso(dt: datetime | None) -> str | None:
        return dt.astimezone(UTC).isoformat() if dt else None

    payload = {
        "job_id": str(job.id),
        "job_version": job.version,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "current_step": job.current_step,
        "retry_count": job.retry_count,
        "created_at": _iso(job.created_at),
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "updated_at": _iso(job.updated_at) or datetime.now(UTC).isoformat(),
        "trace_id": job.trace_id,
    }
    if job.status == "failed" and job.error_code:
        payload["error"] = {
            "code": job.error_code,
            "message": job.error_message,
            "retryable": job.error_retryable,
        }
    if job.entity_type and job.entity_id:
        payload["entity"] = {"type": job.entity_type, "id": str(job.entity_id)}
    if extra:
        payload.update(extra)
    session.add(
        AsyncJobEvent(
            user_id=job.user_id,
            job_id=job.id,
            job_version=job.version,
            event_type=event_type,
            payload_json=payload,
        )
    )


def transition(
    session: Session,
    job: AsyncJob,
    *,
    status: str | None = None,
    progress: int | None = None,
    current_step: str | None = None,
    result: dict | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    error_retryable: bool = False,
    extra_event: dict | None = None,
) -> AsyncJob:
    """Apply a durable transition and append its event in one transaction scope."""
    # A late/stale worker must not resurrect a job the user already cancelled or
    # completed. Failed jobs remain re-activatable via retry_job (failed->queued).
    if job.status in ("completed", "cancelled") and status is not None and status != job.status:
        return job
    now = datetime.now(UTC)
    if status is not None:
        job.status = status
        if status == "queued" and job.queued_at is None:
            job.queued_at = now
        if status == "processing" and job.started_at is None:
            job.started_at = now
        if status in TERMINAL:
            job.finished_at = now
    if progress is not None:
        # Progress must not decrease within an attempt.
        job.progress = max(job.progress, min(100, max(0, progress)))
    if current_step is not None:
        job.current_step = current_step
    if result is not None:
        job.result_json = result
    if error_code is not None:
        job.error_code = error_code
        job.error_message = error_message
        job.error_retryable = error_retryable
    job.version += 1
    job.updated_at = now
    session.flush()
    event_type = _EVENT_FOR_STATUS.get(job.status, "job.updated")
    _append_event(session, job, event_type, extra_event)
    return job


def get_owned_job(session: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> AsyncJob:
    job = session.get(AsyncJob, job_id)
    if job is None or job.user_id != user_id:
        raise NotFoundError("Job not found")
    return job


def request_cancel(session: Session, job: AsyncJob) -> AsyncJob:
    if job.status in TERMINAL:
        raise ConflictError("Job already finished", code="job_finished")
    job.cancel_requested_at = datetime.now(UTC)
    return transition(session, job, status="cancelled", current_step="已取消")


def retry_job(session: Session, job: AsyncJob) -> AsyncJob:
    if job.status != "failed":
        raise ConflictError("Only failed jobs can be retried", code="job_not_failed")
    if not job.error_retryable:
        raise ConflictError("This job is not retryable", code="job_not_retryable")
    job.retry_count += 1
    job.error_code = None
    job.error_message = None
    job.progress = 0
    return transition(session, job, status="queued", current_step="重新排队")


def list_jobs(
    session: Session, user_id: uuid.UUID, statuses: list[str] | None = None, limit: int = 100
) -> list[AsyncJob]:
    stmt = select(AsyncJob).where(AsyncJob.user_id == user_id)
    if statuses:
        stmt = stmt.where(AsyncJob.status.in_(statuses))
    stmt = stmt.order_by(AsyncJob.created_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def events_after(
    session: Session, user_id: uuid.UUID, after_id: int, limit: int = 200
) -> list[AsyncJobEvent]:
    stmt = (
        select(AsyncJobEvent)
        .where(AsyncJobEvent.user_id == user_id, AsyncJobEvent.id > after_id)
        .order_by(AsyncJobEvent.id)
        .limit(limit)
    )
    return list(session.scalars(stmt).all())


def latest_event_id(session: Session, user_id: uuid.UUID) -> int:
    stmt = (
        select(AsyncJobEvent.id)
        .where(AsyncJobEvent.user_id == user_id)
        .order_by(AsyncJobEvent.id.desc())
        .limit(1)
    )
    return session.scalar(stmt) or 0
