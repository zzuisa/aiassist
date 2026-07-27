"""Quick-add planning worker: analyze a line and create tasks (or ask questions)."""

from __future__ import annotations

import uuid

from app.db.session import session_scope
from app.modules.tasks import plan_service
from app.workers.celery_app import celery


@celery.task(name="app.workers.tasks.plan.process_plan", bind=True, max_retries=3)
def process_plan(self, job_id: str) -> str:  # type: ignore[no-untyped-def]
    with session_scope() as s:
        job = plan_service.run_plan(s, uuid.UUID(job_id))
        return job.status
