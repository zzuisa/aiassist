"""Trace IDs cross task creation, fan-out, gateway context and status events."""

from __future__ import annotations

from sqlalchemy import select


def test_trace_id_propagates_into_fanout_and_status_event(db_session, make_user) -> None:
    from app.core.observability import get_trace_id, set_trace_id
    from app.models.foundation import AsyncJobEvent
    from app.modules.agent.runner import WorkItem, run_bounded
    from app.modules.agent.service import create_agent_task, execute_query_task

    trace_id = "a" * 32
    set_trace_id(trace_id)
    try:
        observed = run_bounded(
            [WorkItem(key="one", input_scope={})],
            lambda _item: get_trace_id(),
            max_concurrency=1,
        )
        user = make_user()
        task = create_agent_task(
            db_session,
            user_id=user.id,
            request_text="当前有多少分类",
            intent_key="taxonomy.categories",
        )
        execute_query_task(db_session, task.id)
        event = db_session.scalar(
            select(AsyncJobEvent)
            .where(AsyncJobEvent.job_id == task.job_id, AsyncJobEvent.event_type == "agent.status_changed")
            .order_by(AsyncJobEvent.id)
        )
        assert observed.succeeded[0].value == trace_id
        assert task.job.trace_id == trace_id
        assert event is not None and event.payload_json["trace_id"] == trace_id
    finally:
        set_trace_id(None)
