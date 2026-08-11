"""Celery entry points for durable Agent tasks."""

from __future__ import annotations

import uuid

from app.core.observability import get_logger, set_trace_id
from app.db.session import session_scope
from app.models.agent import AgentTask
from app.models.agent_conversation import AgentTurn
from app.models.foundation import AsyncJob
from app.modules.agent import conversation_service
from app.modules.agent.service import execute_agent_task
from app.workers.celery_app import celery

log = get_logger("agent.worker")


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


@celery.task(name="app.workers.tasks.agent.execute_conversation_turn", bind=True, max_retries=1)
def execute_conversation_turn(self, turn_id: str) -> str:  # type: ignore[no-untyped-def]
    """Route and finalize a single conversation Turn.

    Handles the deterministic chat fast path and the structured conversation
    route that bridges task messages into the existing Agent runtime.
    """
    set_trace_id(None)
    parsed_id = uuid.UUID(turn_id)
    try:
        with session_scope() as session:
            persisted = session.get(AgentTurn, parsed_id)
            if persisted is not None:
                job = session.get(AsyncJob, persisted.job_id)
                if job is not None:
                    set_trace_id(job.trace_id)
            turn = conversation_service.execute_turn(session, parsed_id)
            return turn.status
    except Exception as exc:
        # Preserve only the stable exception class and durable turn ID. Raw
        # provider/config exception text may contain sensitive connection data.
        log.error(
            "conversation_turn_execution_failed",
            turn_id=turn_id,
            error_type=type(exc).__name__,
        )
        with session_scope() as finalizer_session:
            conversation_service.finalize_turn_failure(finalizer_session, parsed_id, exc)
        return "failed"
    finally:
        set_trace_id(None)
