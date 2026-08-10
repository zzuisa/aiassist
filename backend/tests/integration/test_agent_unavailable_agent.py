"""Disabled spec-006 Agents become explicit gaps, never fake runs."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

pytestmark = [pytest.mark.integration]


def test_disabled_illustration_agent_produces_gap_without_running(db_session, make_user) -> None:
    from app.models.agent import AgentRun
    from app.modules.agent.service import create_agent_task, execute_agent_task

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="为文章生成一张概念插画",
        intent_key="capability.unknown",
    )
    db_session.commit()

    completed = execute_agent_task(db_session, task.id)
    db_session.commit()
    reply = json.loads(completed.result_summary or "{}")
    runs = list(db_session.scalars(select(AgentRun).where(AgentRun.task_id == task.id)).all())

    assert any("illustration-agent" in item for item in reply["能力缺口"]["缺失能力"])
    assert all(run.agent_key != "illustration-agent" for run in runs)
    assert all(run.current_tool is None for run in runs)
