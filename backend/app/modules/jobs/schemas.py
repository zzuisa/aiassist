"""Job serialization shared by the jobs router and other modules."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.foundation import AsyncJob


class JobError(BaseModel):
    code: str
    message: str
    retryable: bool


class EntityRef(BaseModel):
    type: str
    id: uuid.UUID


class AsyncJobOut(BaseModel):
    id: uuid.UUID
    job_type: str
    entity: EntityRef | None = None
    status: str
    priority: int
    progress: int
    current_step: str | None = None
    result: dict[str, Any] | None = None
    error: JobError | None = None
    retry_count: int
    trace_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    updated_at: datetime
    finished_at: datetime | None = None


def serialize_job(job: AsyncJob) -> AsyncJobOut:
    entity = None
    if job.entity_type and job.entity_id:
        entity = EntityRef(type=job.entity_type, id=job.entity_id)
    error = None
    if job.error_code:
        error = JobError(
            code=job.error_code,
            message=job.error_message or "",
            retryable=job.error_retryable,
        )
    return AsyncJobOut(
        id=job.id,
        job_type=job.job_type,
        entity=entity,
        status=job.status,
        priority=job.priority,
        progress=job.progress,
        current_step=job.current_step,
        result=job.result_json,
        error=error,
        retry_count=job.retry_count,
        trace_id=job.trace_id,
        created_at=job.created_at,
        started_at=job.started_at,
        updated_at=job.updated_at,
        finished_at=job.finished_at,
    )
