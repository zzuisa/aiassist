"""Write tools cannot mutate business data before structured approval."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]


def test_pending_write_leaves_post_unchanged_and_tool_is_denied(db_session, make_user) -> None:
    from app.core.errors import ConflictError
    from app.models.agent import AgentRun
    from app.modules.agent.registry import ToolContext, tool_registry
    from app.modules.agent.service import create_agent_task, create_pending_write
    from app.modules.posts import service as post_service

    user = make_user()
    post = post_service.create_post(db_session, user.id, title="标题", markdown="正文")
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="生成摘要并保存",
        intent_key="articles.analyze",
    )
    run = AgentRun(
        task_id=task.id,
        agent_key="editor-agent",
        agent_version="test-v1",
        agent_name="编辑 Agent",
        responsibility="分析文章",
        current_task=task.request_text,
        allowed_tools=["posts.apply_analysis"],
        status="running",
    )
    db_session.add(run)
    db_session.flush()
    pending = create_pending_write(
        db_session,
        task=task,
        run=run,
        operation_type="update",
        target_type="post",
        targets=[{"id": str(post.id), "version": post.version}],
        preview={
            "summary": "保存生成结果",
            "changes": [{"post_id": str(post.id), "summary": "新摘要", "tags": [], "keywords": []}],
        },
        reversible=True,
        tool_name="posts.apply_analysis",
    )
    original_version = post.version

    with pytest.raises(ConflictError, match="approval"):
        tool_registry.invoke(
            "posts.apply_analysis",
            context=ToolContext(
                user_id=user.id,
                task_id=task.id,
                run_id=run.id,
                session=db_session,
            ),
            params={"confirmation_id": str(pending.id)},
        )

    db_session.refresh(post)
    assert post.summary is None
    assert post.version == original_version
    assert task.status == "waiting_confirmation"
    assert run.allow_write is False
