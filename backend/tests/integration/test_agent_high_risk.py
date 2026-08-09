"""High-risk writes always remain behind a second confirmation."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


@pytest.mark.parametrize(
    ("operation_type", "targets", "preview"),
    [
        ("delete", [{"id": "d75b4cd6-f20f-44ba-a003-4b96b777688e", "version": 1}], {}),
        (
            "update",
            [{"id": "d75b4cd6-f20f-44ba-a003-4b96b777688e", "version": 1}],
            {"overwrite": True},
        ),
        (
            "update",
            [
                {"id": "d75b4cd6-f20f-44ba-a003-4b96b777688e", "version": 1},
                {"id": "50ea3d47-e8f5-4868-af12-6b55e0ce71f7", "version": 1},
            ],
            {},
        ),
    ],
)
def test_high_risk_operation_waits_even_when_request_already_said_proceed(
    db_session, make_user, operation_type, targets, preview
) -> None:
    from app.models.agent import AgentRun
    from app.modules.agent.service import create_agent_task, create_pending_write

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="我确认，请直接执行",
        intent_key="articles.analyze",
    )
    run = AgentRun(
        task_id=task.id,
        agent_key="editor-agent",
        agent_version="test-v1",
        agent_name="编辑 Agent",
        responsibility="修改文章",
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
        operation_type=operation_type,
        target_type="post",
        targets=targets,
        preview=preview,
        reversible=operation_type != "delete",
        tool_name="posts.apply_analysis",
        original_request_confirmed=True,
    )

    assert pending.high_risk is True
    assert pending.decision == "pending"
    assert task.status == "waiting_confirmation"
    assert run.status == "waiting_confirmation"
    assert run.allow_write is False
