"""Jobs REST + SSE routes. Retry/cancel are refined in US6 (T095)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.core.errors import AuthenticationError
from app.db.session import get_db
from app.modules.auth import service as auth_service
from app.modules.jobs import service as jobs_service
from app.modules.jobs.schemas import AsyncJobOut, ClearCompletedJobsOut, serialize_job
from app.modules.jobs.sse import event_stream

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[AsyncJobOut])
def list_jobs(
    status: list[str] | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AsyncJobOut]:
    jobs = jobs_service.list_jobs(db, user.id, statuses=status)
    return [serialize_job(j) for j in jobs]


@router.delete("/jobs/completed", response_model=ClearCompletedJobsOut)
def clear_completed_jobs(
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ClearCompletedJobsOut:
    deleted_count = jobs_service.clear_completed_jobs(db, user.id)
    db.commit()
    return ClearCompletedJobsOut(deleted_count=deleted_count)


@router.get("/jobs/{job_id}", response_model=AsyncJobOut)
def get_job(
    job_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AsyncJobOut:
    job = jobs_service.get_owned_job(db, user.id, job_id)
    return serialize_job(job)


@router.post("/jobs/{job_id}/retry", response_model=AsyncJobOut, status_code=202)
def retry_job(
    job_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> AsyncJobOut:
    job = jobs_service.get_owned_job(db, user.id, job_id)
    job = jobs_service.retry_job(db, job)
    db.commit()
    return serialize_job(job)


@router.post("/jobs/{job_id}/cancel", response_model=AsyncJobOut, status_code=202)
def cancel_job(
    job_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> AsyncJobOut:
    job = jobs_service.get_owned_job(db, user.id, job_id)
    job = jobs_service.request_cancel(db, job)
    db.commit()
    return serialize_job(job)


@router.get("/events/jobs")
def stream_jobs(request: Request, db: Session = Depends(get_db)) -> StreamingResponse:
    # Validate the access session before opening the stream.
    access_cookie, _ = auth_service.auth_cookie_names()
    token = request.cookies.get(access_cookie)
    if not token:
        raise AuthenticationError("Authentication required")
    claims = auth_service.decode_access_token(token)
    user_id = uuid.UUID(claims["sub"])
    last_event_id = request.headers.get("Last-Event-ID")
    return StreamingResponse(
        event_stream(user_id, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
