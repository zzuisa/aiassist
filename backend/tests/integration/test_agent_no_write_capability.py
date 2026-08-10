"""Generated results remain useful when no matching write capability exists."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


def test_missing_write_tool_reports_generated_but_not_saved(db_session, make_user) -> None:
    from app.models.agent import AgentRun, PendingWrite
    from app.modules.agent.service import create_agent_task, prepare_pending_write

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="生成结果并保存到不存在的系统",
        intent_key="articles.analyze",
    )
    run = AgentRun(
        task_id=task.id,
        agent_key="editor-agent",
        agent_version="test-v1",
        agent_name="编辑 Agent",
        responsibility="分析文章",
        current_task=task.request_text,
        allowed_tools=[],
        status="running",
    )
    db_session.add(run)
    db_session.flush()

    pending, message = prepare_pending_write(
        db_session,
        task=task,
        run=run,
        operation_type="update",
        target_type="external_record",
        targets=[],
        preview={"generated": [{"value": "结果仍可查看"}]},
        reversible=False,
        tool_name="external.save",
    )

    assert pending is None
    assert "已生成" in message
    assert "无法保存" in message
    assert db_session.query(PendingWrite).filter(PendingWrite.task_id == task.id).count() == 0
    assert run.allow_write is False
