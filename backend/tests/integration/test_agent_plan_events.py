"""Plan events are durable, replayable and present in reconnect snapshots."""

from __future__ import annotations

import pytest
from sqlalchemy import select

pytestmark = [pytest.mark.integration]


async def test_plan_event_replay_and_snapshot(db_session, make_user) -> None:
    from app.models.foundation import AsyncJobEvent
    from app.modules.agent.planning_schemas import AgentTaskPlanProposal
    from app.modules.agent.planning_service import persist_plan
    from app.modules.agent.service import create_agent_task
    from app.modules.agent.status import publish_plan_event
    from app.modules.jobs.sse import _snapshot_payload, event_stream

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="查询文章",
        intent_key="articles.list_recent",
    )
    proposal = AgentTaskPlanProposal.model_validate(
        {
            "objective": "查询文章",
            "steps": [
                {
                    "step_key": "step_query",
                    "title": "查询文章",
                    "responsibility": "取得文章范围",
                    "tool_name": "posts.list_recent",
                    "operation_type": "query",
                    "arguments": {"limit": 2},
                    "depends_on": [],
                    "input_source": "current_message",
                    "expected_output": "文章 ID",
                    "requires_confirmation": False,
                }
            ],
        }
    )
    plan = persist_plan(db_session, task=task, proposal=proposal)
    first = db_session.scalar(
        select(AsyncJobEvent).where(AsyncJobEvent.job_id == task.job_id).order_by(AsyncJobEvent.id)
    )
    event = publish_plan_event(db_session, plan)
    db_session.commit()
    assert first is not None

    snapshot, cursor = _snapshot_payload(user.id)
    assert cursor >= event.id
    assert any(item["plan_id"] == str(plan.id) for item in snapshot["plans"])

    stream = event_stream(user.id, str(first.id))
    frame = await anext(stream)
    await stream.aclose()
    assert f"id: {event.id}" in frame
    assert "event: agent.plan_updated" in frame
    assert str(plan.id) in frame
