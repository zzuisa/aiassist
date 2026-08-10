"""The first public Agent status event is emitted within two seconds."""

from __future__ import annotations

from time import monotonic

from sqlalchemy import select


def test_first_agent_status_event_latency_is_below_two_seconds(db_session, make_user) -> None:
    from app.models.foundation import AsyncJobEvent
    from app.modules.agent.service import create_agent_task, execute_query_task

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="当前有多少标签",
        intent_key="taxonomy.tags",
    )
    db_session.commit()
    started = monotonic()
    execute_query_task(db_session, task.id)
    db_session.flush()
    first = db_session.scalar(
        select(AsyncJobEvent)
        .where(AsyncJobEvent.job_id == task.job_id, AsyncJobEvent.event_type == "agent.status_changed")
        .order_by(AsyncJobEvent.id)
    )
    assert first is not None
    assert monotonic() - started <= 2.0
