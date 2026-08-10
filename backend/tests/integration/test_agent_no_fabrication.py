"""Unregistered tools cannot be called or represented by fake output."""

from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.integration]


def test_unregistered_tool_is_rejected_and_no_mock_result_is_created(
    db_session,
    make_user,
) -> None:
    from app.core.errors import ValidationError
    from app.modules.agent.registry import ToolContext, tool_registry
    from app.modules.agent.service import create_agent_task, execute_agent_task

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="调用 imaginary.crm.sync 并返回同步结果",
        intent_key="capability.unknown",
    )
    db_session.commit()

    with pytest.raises(ValidationError, match="not registered"):
        tool_registry.invoke(
            "imaginary.crm.sync",
            context=ToolContext(user_id=user.id, task_id=task.id, session=db_session),
            params={},
        )

    completed = execute_agent_task(db_session, task.id)
    reply = json.loads(completed.result_summary or "{}")
    rendered = json.dumps(reply, ensure_ascii=False).casefold()
    assert "能力缺口" in reply
    assert "mock" not in rendered
    assert "模拟数据" not in rendered
    assert "同步成功" not in rendered
