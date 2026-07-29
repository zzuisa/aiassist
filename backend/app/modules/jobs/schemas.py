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
    # Derived (spec 005, T024). Presentation-only; never persisted as status.
    scope: str | None = None
    business_stage: str | None = None
    display_status: str | None = None


# ---------------------------------------------------------------------------
# Blog job derivation (spec 005, T024)
#
# The generic job status ('pending'/'queued'/'processing'/'completed'/…) stays
# the single stored truth. For blog jobs we additionally *derive* a scope, a
# business stage and a user-facing display status purely from the job_type,
# current_step and status — nothing is written back.
# ---------------------------------------------------------------------------

_BLOG_JOB_PREFIX = "blog."

# job_type suffix → business stage.
_BLOG_STAGE_BY_TYPE = {
    "blog.capture": "capturing",
    "blog.parse": "parsing",
    "blog.generate": "optimizing",
    "blog.optimize": "optimizing",
    "blog.wordcloud": "aggregating",
}

# (business_stage, generic status) → display status shown to the user.
_DISPLAY_STATUS = {
    ("capturing", "processing"): "capturing",
    ("parsing", "processing"): "parsing",
    ("optimizing", "queued"): "ai_queued",
    ("optimizing", "pending"): "ai_queued",
    ("optimizing", "processing"): "ai_processing",
    ("optimizing", "completed"): "ai_review",
    ("aggregating", "processing"): "aggregating",
}


def _derive_blog_fields(job: AsyncJob) -> tuple[str | None, str | None, str | None]:
    if not job.job_type.startswith(_BLOG_JOB_PREFIX):
        return None, None, None
    scope = "blog"
    stage = _BLOG_STAGE_BY_TYPE.get(job.job_type, "processing")
    if job.status == "failed":
        display = "failed"
    elif job.status == "cancelled":
        display = "cancelled"
    else:
        display = _DISPLAY_STATUS.get((stage, job.status), job.status)
    return scope, stage, display


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
    scope, business_stage, display_status = _derive_blog_fields(job)
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
        scope=scope,
        business_stage=business_stage,
        display_status=display_status,
    )
