"""Clearing completed jobs removes Agent history but never business posts."""

from __future__ import annotations

import pytest
from app.models.agent import AgentRun, AgentTask, ExecutionRecord, PendingWrite
from app.models.posts import Post
from app.modules.agent.audit import write_execution_record
from app.modules.agent.service import create_agent_task
from app.modules.jobs import service as jobs_service
from sqlalchemy import func, select

pytestmark = [pytest.mark.integration]


def _count(db_session, model: type) -> int:
    return int(db_session.scalar(select(func.count()).select_from(model)) or 0)


def test_clear_completed_jobs_cascades_agent_tables_but_preserves_posts(
    db_session, make_user
) -> None:
    user = make_user()
    post = Post(user_id=user.id, title="必须保留的文章", markdown="正文", status="private")
    db_session.add(post)
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="处理这篇文章",
        intent_key="test.cascade",
    )
    run = AgentRun(
        task_id=task.id,
        agent_key="test-agent",
        agent_version="v1",
        agent_name="测试 Agent",
        responsibility="验证级联",
        current_task="读取文章元数据",
        input_scope_json={"post_ids": [str(post.id)]},
        status="success",
    )
    db_session.add(run)
    db_session.flush()
    write_execution_record(
        db_session,
        task_id=task.id,
        run_id=run.id,
        step_id="step-1",
        agent_name=run.agent_name,
        step_label="读取文章元数据",
        tool_name="posts.read_metadata",
        operation_type="query",
        params={"post_id": str(post.id)},
        status="success",
    )
    db_session.add(
        PendingWrite(
            task_id=task.id,
            run_id=run.id,
            operation_type="update",
            target_type="post",
            targets_json=[{"id": str(post.id), "version": 1}],
            preview_json={"title": "预览，不应落库"},
            affected_count=1,
            reversible=True,
            high_risk=False,
        )
    )
    jobs_service.transition(db_session, task.job, status="completed", progress=100)
    db_session.commit()

    assert [_count(db_session, model) for model in (AgentTask, AgentRun, ExecutionRecord, PendingWrite)] == [1, 1, 1, 1]
    post_id = post.id

    assert jobs_service.clear_completed_jobs(db_session, user.id) == 1
    db_session.commit()

    assert [_count(db_session, model) for model in (AgentTask, AgentRun, ExecutionRecord, PendingWrite)] == [0, 0, 0, 0]
    assert db_session.get(Post, post_id) is not None
