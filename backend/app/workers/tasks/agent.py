"""Celery entry points for durable Agent tasks."""

from __future__ import annotations

import uuid

from app.core.observability import set_trace_id
from app.db.session import session_scope
from app.models.agent import AgentTask
from app.modules.agent.service import execute_agent_task
from app.workers.celery_app import celery


@celery.task(name="app.workers.tasks.agent.execute_task", bind=True, max_retries=1)
def execute_task(self, task_id: str) -> str:  # type: ignore[no-untyped-def]
    """Execute a persisted query intent and return its durable terminal state."""
    set_trace_id(None)
    try:
        with session_scope() as session:
            parsed_id = uuid.UUID(task_id)
            persisted = session.get(AgentTask, parsed_id)
            if persisted is not None:
                set_trace_id(persisted.job.trace_id)
            task = execute_agent_task(session, parsed_id)
            return task.status
    finally:
        set_trace_id(None)
