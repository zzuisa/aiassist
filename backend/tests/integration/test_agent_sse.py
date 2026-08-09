"""Agent status events are durable, replayable, and represented in snapshots."""

from __future__ import annotations

import pytest
from sqlalchemy import select

pytestmark = [pytest.mark.integration]


def test_agent_status_event_is_persisted_and_snapshot_contains_running_agent(
    db_session, make_user
) -> None:
    from app.models.agent import AgentRun
    from app.models.foundation import AsyncJobEvent
    from app.modules.agent.service import create_agent_task
    from app.modules.agent.status import publish_status
    from app.modules.jobs.sse import _snapshot_payload

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="给我最近 10 篇文章",
        intent_key="articles.list_recent",
    )
    run = AgentRun(
        task_id=task.id,
        agent_key="article-query-agent",
        agent_version="runtime-query-v1",
        agent_name="文章查询 Agent",
        responsibility="查询文章元数据",
        current_task=task.request_text,
        status="running",
        stage_label="正在查询",
    )
    db_session.add(run)
    task.status = "running"
    db_session.flush()
    publish_status(db_session, task, run)
    db_session.commit()

    event = db_session.scalar(
        select(AsyncJobEvent)
        .where(
            AsyncJobEvent.job_id == task.job_id,
            AsyncJobEvent.event_type == "agent.status_changed",
        )
        .order_by(AsyncJobEvent.id.desc())
    )
    assert event is not None
    assert event.payload_json["task_id"] == str(task.id)

    snapshot, cursor = _snapshot_payload(user.id)
    assert cursor >= event.id
    assert any(item["agent"]["agent_id"] == str(run.id) for item in snapshot["agents"])


async def test_agent_status_replays_after_last_event_id_and_invalid_cursor_snapshots(
    db_session, make_user
) -> None:
    from app.models.agent import AgentRun
    from app.models.foundation import AsyncJobEvent
    from app.modules.agent.service import create_agent_task
    from app.modules.agent.status import publish_status
    from app.modules.jobs.sse import event_stream

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="统计文章分类",
        intent_key="taxonomy.categories",
    )
    run = AgentRun(
        task_id=task.id,
        agent_key="article-query-agent",
        agent_version="runtime-query-v1",
        agent_name="文章查询 Agent",
        responsibility="统计文章分类",
        current_task=task.request_text,
        status="running",
        stage_label="正在统计",
    )
    db_session.add(run)
    task.status = "running"
    db_session.flush()
    initial_event = db_session.scalar(
        select(AsyncJobEvent).where(AsyncJobEvent.job_id == task.job_id).order_by(AsyncJobEvent.id)
    )
    assert initial_event is not None
    status_event = publish_status(db_session, task, run)
    db_session.commit()

    replay = event_stream(user.id, str(initial_event.id))
    frame = await anext(replay)
    await replay.aclose()
    assert f"id: {status_event.id}" in frame
    assert "event: agent.status_changed" in frame
    assert '"status": "running"' in frame

    resync = event_stream(user.id, str(status_event.id + 1000))
    snapshot_frame = await anext(resync)
    await resync.aclose()
    assert "event: jobs.snapshot" in snapshot_frame
    assert str(run.id) in snapshot_frame
