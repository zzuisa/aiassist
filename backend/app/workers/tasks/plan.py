"""Quick-add planning worker: analyze a line and create tasks (or ask questions)."""

from __future__ import annotations

import uuid

from app.db.session import session_scope
from app.modules.tasks import plan_service
from app.workers.celery_app import celery

_ANSWER_TIMEOUT_SECONDS = 180  # 3 minutes, then record with defaults


@celery.task(name="app.workers.tasks.plan.process_plan", bind=True, max_retries=3)
def process_plan(self, job_id: str) -> str:  # type: ignore[no-untyped-def]
    with session_scope() as s:
        job = plan_service.run_plan(s, uuid.UUID(job_id))
        status = job.status
    # If it is waiting on the user, auto-record with defaults after the timeout
    # (the job stays answerable so the user can still refine).
    if status == "waiting_user":
        process_plan_expire.apply_async((job_id,), countdown=_ANSWER_TIMEOUT_SECONDS)
    return status


@celery.task(name="app.workers.tasks.plan.process_plan_expire")
def process_plan_expire(job_id: str) -> str:
    with session_scope() as s:
        job = plan_service.expire_plan(s, uuid.UUID(job_id))
        return job.status if job else "gone"
