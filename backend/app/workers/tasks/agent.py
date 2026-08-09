"""Celery entry points for durable Agent tasks."""

from __future__ import annotations

import uuid

from app.db.session import session_scope
from app.modules.agent.service import execute_agent_task
from app.workers.celery_app import celery


@celery.task(name="app.workers.tasks.agent.execute_task", bind=True, max_retries=1)
def execute_task(self, task_id: str) -> str:  # type: ignore[no-untyped-def]
    """Execute a persisted query intent and return its durable terminal state."""
    with session_scope() as session:
        task = execute_agent_task(session, uuid.UUID(task_id))
        return task.status
