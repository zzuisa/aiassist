"""LangGraph runtime for bounded Agent plans.

The graph is intentionally fixed.  The model can propose data in the plan
schema, but it cannot create executable nodes or call MCP clients directly.
Existing domain services remain responsible for authorization, confirmation,
idempotency, optimistic locking, and post-condition verification.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from typing import Any, Literal, TypedDict

from app.core.config import get_settings
from app.core.observability import get_logger
from app.db.session import session_scope
from app.models.agent import AgentExecutionPlan
from app.modules.agent import scheduler as projection_service
from app.modules.agent import step_executor

log = get_logger("agent.graph")


class AgentGraphState(TypedDict, total=False):
    plan_id: str
    ready_step_ids: list[str]
    status: str
    iterations: int


def _execute_claimed_step(step_id: uuid.UUID) -> uuid.UUID | None:
    """Execute a claimed operator using isolated transactional sessions."""
    try:
        with session_scope() as session:
            projection_service.start_step(session, step_id)
        with session_scope() as session:
            return step_executor.execute_step(session, step_id)
    except Exception as exc:
        with session_scope() as session:
            return projection_service.fail_step(session, step_id, exc)


def _dispatch_ready(state: AgentGraphState) -> dict[str, object]:
    plan_id = uuid.UUID(state["plan_id"])
    with session_scope() as session:
        step_ids = projection_service.coordinate_plan(session, plan_id)
        plan = session.get(AgentExecutionPlan, plan_id)
        status = plan.status if plan is not None else "failed"
    return {
        "ready_step_ids": [str(step_id) for step_id in step_ids],
        "status": status,
        "iterations": state.get("iterations", 0) + 1,
    }


def _execute_ready(state: AgentGraphState) -> dict[str, object]:
    step_ids = [uuid.UUID(value) for value in state.get("ready_step_ids", [])]
    if not step_ids:
        return {"status": state.get("status", "unknown")}
    max_workers = min(get_settings().agent_plan_max_concurrency, len(step_ids))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent-graph") as pool:
        futures = [
            pool.submit(copy_context().run, _execute_claimed_step, step_id) for step_id in step_ids
        ]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:  # siblings continue; projection records the failure
                log.error("agent_graph_operator_failed", error_type=type(exc).__name__)
    return {"ready_step_ids": []}


def _route(state: AgentGraphState) -> Literal["execute", "continue", "finish"]:
    if state.get("ready_step_ids"):
        return "execute"
    if state.get("status") in {"waiting_user", "success", "partial_success", "failed", "cancelled"}:
        return "finish"
    # A bounded guard prevents malformed legacy projections from spinning forever.
    if state.get("iterations", 0) >= 32:
        return "finish"
    return "continue"


def build_agent_graph(*, checkpointer: Any | None = None) -> Any:
    """Build the single safe orchestration graph.

    ``checkpointer`` is injected by the worker/runtime composition root.  The
    graph remains testable without infrastructure, while production supplies
    the PostgreSQL checkpointer from ``langgraph-checkpoint-postgres``.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:  # pragma: no cover - dependency packaging guard
        raise RuntimeError("LangGraph dependencies are not installed") from exc

    graph = StateGraph(AgentGraphState)
    graph.add_node("dispatch_ready_steps", _dispatch_ready)
    graph.add_node("execute_operators", _execute_ready)
    graph.add_edge(START, "dispatch_ready_steps")
    graph.add_conditional_edges(
        "dispatch_ready_steps",
        _route,
        {"execute": "execute_operators", "continue": "dispatch_ready_steps", "finish": END},
    )
    graph.add_edge("execute_operators", "dispatch_ready_steps")
    return graph.compile(checkpointer=checkpointer)


def run_agent_graph(plan_id: uuid.UUID, *, checkpointer: Any | None = None) -> AgentGraphState:
    """Invoke or resume one plan using ``plan_id`` as the LangGraph thread."""
    config = {"configurable": {"thread_id": str(plan_id)}}
    run_id = str(uuid.uuid4())
    with session_scope() as session:
        plan = session.get(AgentExecutionPlan, plan_id)
        if plan is None:
            raise ValueError("Agent plan not found")
        plan.graph_thread_id = str(plan_id)
        plan.graph_run_id = run_id
        plan.runtime_state = "running"
    if checkpointer is not None:
        graph = build_agent_graph(checkpointer=checkpointer)
        result = graph.invoke({"plan_id": str(plan_id), "iterations": 0}, config=config)
        _mark_runtime_terminal(plan_id, result)
        return result

    # The worker owns the checkpointer lifecycle.  Keeping this composition
    # here avoids a second state store and makes local/unit graph construction
    # possible without opening a database connection.
    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        from app.core.config import get_settings
    except ImportError as exc:  # pragma: no cover - dependency packaging guard
        raise RuntimeError("Postgres LangGraph checkpointer is not installed") from exc

    dsn = get_settings().sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.setup()
        graph = build_agent_graph(checkpointer=saver)
        try:
            result = graph.invoke({"plan_id": str(plan_id), "iterations": 0}, config=config)
        except Exception:
            with session_scope() as session:
                plan = session.get(AgentExecutionPlan, plan_id)
                if plan is not None:
                    plan.runtime_state = "failed"
            raise
        _mark_runtime_terminal(plan_id, result)
        return result


def _mark_runtime_terminal(plan_id: uuid.UUID, result: AgentGraphState) -> None:
    with session_scope() as session:
        plan = session.get(AgentExecutionPlan, plan_id)
        if plan is None:
            return
        plan.runtime_state = (
            "interrupted" if result.get("status") == "waiting_user" else "completed"
        )
