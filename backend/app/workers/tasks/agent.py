"""Celery entry points for durable Agent tasks."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.observability import get_logger, set_trace_id
from app.db.session import session_scope
from app.models.agent import AgentExecutionPlan, AgentPlanStep, AgentTask
from app.models.agent_conversation import AgentTurn
from app.models.foundation import AsyncJob
from app.modules.agent import conversation_service
from app.workers.celery_app import celery

log = get_logger("agent.worker")


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
            conversation_service.begin_turn_routing(session, parsed_id)
        with session_scope() as session:
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
    """Invoke or resume the single LangGraph run for this plan."""
    set_trace_id(None)
    parsed_id = uuid.UUID(plan_id)
    try:
        from app.modules.agent.graph_runtime import run_agent_graph

        result = run_agent_graph(parsed_id)
        return f"graph:{result.get('status', 'completed')}"
    finally:
        set_trace_id(None)


@celery.task(name="app.workers.tasks.agent.execute_plan_step", bind=True, max_retries=1)
def execute_plan_step(self, step_id: str) -> str:  # type: ignore[no-untyped-def]
    """Compatibility shim: resume the owning Graph Run, never execute a step directly."""
    set_trace_id(None)
    parsed_id = uuid.UUID(step_id)
    try:
        with session_scope() as session:
            plan_id = session.scalar(
                select(AgentExecutionPlan.id)
                .join(AgentPlanStep, AgentPlanStep.plan_id == AgentExecutionPlan.id)
                .where(AgentPlanStep.id == parsed_id)
            )
        if plan_id is None:
            return "ignored"
        coordinate_plan.delay(str(plan_id))
        return "graph_resumed"
    finally:
        set_trace_id(None)
