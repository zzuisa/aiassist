"""Celery entry points for durable Agent tasks."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context

from sqlalchemy import select

from app.core.config import get_settings
from app.core.observability import get_logger, set_trace_id
from app.db.session import session_scope
from app.models.agent import AgentExecutionPlan, AgentPlanStep, AgentTask
from app.models.agent_conversation import AgentTurn
from app.models.foundation import AsyncJob
from app.modules.agent import conversation_service, step_executor
from app.modules.agent import scheduler as plan_scheduler
from app.workers.celery_app import celery

log = get_logger("agent.worker")


def _execute_claimed_step(step_id: uuid.UUID) -> uuid.UUID | None:
    """Run one durable step with an isolated session; failures remain step-local."""
    try:
        with session_scope() as session:
            claimed = plan_scheduler.start_step(session, step_id)
            if claimed is None:
                return session.scalar(
                    select(AgentExecutionPlan.id)
                    .join(AgentPlanStep, AgentPlanStep.plan_id == AgentExecutionPlan.id)
                    .where(AgentPlanStep.id == step_id)
                )
        with session_scope() as session:
            return step_executor.execute_step(session, step_id)
    except Exception as exc:
        with session_scope() as session:
            return plan_scheduler.fail_step(session, step_id, exc)


def _execute_ready_batch(step_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Execute one dependency-ready set concurrently within the heavy-worker slot."""
    if not step_ids:
        return []
    max_workers = min(get_settings().agent_plan_max_concurrency, len(step_ids))
    results: list[uuid.UUID] = []
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent-plan") as pool:
        futures = [
            pool.submit(copy_context().run, _execute_claimed_step, step_id) for step_id in step_ids
        ]
        for future in as_completed(futures):
            try:
                plan_id = future.result()
            except Exception as exc:  # preserve sibling work and let the watchdog repair state
                log.error("agent_plan_batch_step_failed", error_type=type(exc).__name__)
                continue
            if plan_id is not None:
                results.append(plan_id)
    return results


@celery.task(name="app.workers.tasks.agent.execute_task", bind=True, max_retries=1)
def execute_task(self, task_id: str) -> str:  # type: ignore[no-untyped-def]
    """Plan a legacy AgentTask, then hand its durable graph to the coordinator."""
    set_trace_id(None)
    try:
        with session_scope() as session:
            parsed_id = uuid.UUID(task_id)
            persisted = session.get(AgentTask, parsed_id)
            if persisted is not None:
                set_trace_id(persisted.job.trace_id)
            task = session.get(AgentTask, parsed_id)
            if task is None:
                return "missing"
            from app.modules.agent.planning_service import persist_legacy_task_plan
            from app.modules.agent.status import publish_plan_event

            plan = persist_legacy_task_plan(session, task)
            publish_plan_event(session, plan)
            plan_id = plan.id
        coordinate_plan.delay(str(plan_id))
        return "planned"
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
            plan_id = session.scalar(
                select(AgentExecutionPlan.id).where(AgentExecutionPlan.turn_id == turn.id)
            )
            status = turn.status
        if plan_id is not None:
            coordinate_plan.delay(str(plan_id))
        return status
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


@celery.task(name="app.workers.tasks.agent.coordinate_plan", bind=True, max_retries=2)
def coordinate_plan(self, plan_id: str) -> str:  # type: ignore[no-untyped-def]
    """Claim ready plan steps, commit their queued state, then dispatch them."""
    set_trace_id(None)
    parsed_id = uuid.UUID(plan_id)
    try:
        with session_scope() as session:
            step_ids = plan_scheduler.coordinate_plan(session, parsed_id)
        if len(step_ids) > 1:
            _execute_ready_batch(step_ids)
            coordinate_plan.delay(str(parsed_id))
        else:
            for step_id in step_ids:
                execute_plan_step.delay(str(step_id))
        return f"queued:{len(step_ids)}"
    finally:
        set_trace_id(None)


@celery.task(name="app.workers.tasks.agent.execute_plan_step", bind=True, max_retries=1)
def execute_plan_step(self, step_id: str) -> str:  # type: ignore[no-untyped-def]
    """Execute one database-claimed step and wake the coordinator afterward."""
    set_trace_id(None)
    parsed_id = uuid.UUID(step_id)
    plan_id: uuid.UUID | None = None
    try:
        plan_id = _execute_claimed_step(parsed_id)
        if plan_id is None:
            return "ignored"
        coordinate_plan.delay(str(plan_id))
        return "completed"
    finally:
        set_trace_id(None)
