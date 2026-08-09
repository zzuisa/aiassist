"""Agent status events expose presentation state only."""

from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.security]


def test_status_event_has_no_prompt_reasoning_or_credentials(db_session, make_user) -> None:
    from app.models.agent import AgentRun
    from app.modules.agent.service import create_agent_task
    from app.modules.agent.status import build_status_payload

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
        responsibility="统计归属用户的文章分类",
        current_task=task.request_text,
        status="running",
        stage_label="正在查询",
    )
    db_session.add(run)
    db_session.flush()

    rendered = json.dumps(build_status_payload(task, run), ensure_ascii=False).casefold()
    for forbidden in (
        "system_prompt",
        "reasoning",
        "chain_of_thought",
        "authorization",
        "bearer ",
        "api_key",
        "cookie",
        "private_key",
    ):
        assert forbidden not in rendered
