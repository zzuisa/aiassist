"""Approved Agent writes reuse owned, optimistic-locking domain services."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


def _pending_summary_update(session, user_id, post, *, target_version: int):
    from app.models.agent import AgentRun
    from app.modules.agent.service import create_agent_task, create_pending_write

    task = create_agent_task(
        session,
        user_id=user_id,
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
    session.add(run)
    session.flush()
    pending = create_pending_write(
        session,
        task=task,
        run=run,
        operation_type="update",
        target_type="post",
        targets=[{"id": str(post.id), "version": target_version}],
        preview={
            "summary": "保存生成结果",
            "changes": [
                {"post_id": str(post.id), "summary": "审批后的摘要", "tags": [], "keywords": []}
            ],
        },
        reversible=True,
        tool_name="posts.apply_analysis",
    )
    return task, pending


def test_approved_write_updates_owned_post(db_session, make_user) -> None:
    from app.modules.agent.service import decide_pending_write
    from app.modules.posts import service as post_service

    user = make_user()
    post = post_service.create_post(db_session, user.id, title="标题", markdown="正文")
    original_version = post.version
    task, pending = _pending_summary_update(
        db_session, user.id, post, target_version=original_version
    )

    decided = decide_pending_write(
        db_session,
        user_id=user.id,
        task_id=task.id,
        confirmation_id=pending.id,
        decision="approve",
    )

    db_session.refresh(post)
    assert decided.decision == "approved"
    assert post.summary == "审批后的摘要"
    assert post.version == original_version + 1
    assert task.status == "success"


def test_approved_write_rechecks_optimistic_version(db_session, make_user) -> None:
    from app.core.errors import VersionConflictError
    from app.modules.agent.service import decide_pending_write
    from app.modules.posts import service as post_service

    user = make_user()
    post = post_service.create_post(db_session, user.id, title="标题", markdown="正文")
    task, pending = _pending_summary_update(db_session, user.id, post, target_version=post.version)
    post.version += 1
    db_session.flush()

    with pytest.raises(VersionConflictError):
        decide_pending_write(
            db_session,
            user_id=user.id,
            task_id=task.id,
            confirmation_id=pending.id,
            decision="approve",
        )

    assert post.summary is None


def test_analysis_save_request_waits_then_applies_generated_metadata(db_session, make_user) -> None:
    from app.models.agent import PendingWrite
    from app.models.blog import PostKeywordLink
    from app.models.posts import PostTag
    from app.modules.agent.service import (
        create_agent_task,
        decide_pending_write,
        execute_analysis_task,
    )
    from app.modules.posts import service as post_service

    user = make_user()
    post = post_service.create_post(db_session, user.id, title="Agent 文章", markdown="正文")
    original_version = post.version
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="提取标签和关键词并保存",
        intent_key="articles.analyze",
        scope={"object_ids": [str(post.id)]},
    )

    execute_analysis_task(
        db_session,
        task.id,
        analyze_post=lambda item, _request: {
            "post_id": item["id"],
            "tags": ["Agent"],
            "keywords": ["确认流程"],
            "summary": "审批前只生成，审批后保存。",
        },
    )

    pending = db_session.query(PendingWrite).filter(PendingWrite.task_id == task.id).one()
    db_session.refresh(post)
    assert task.status == "waiting_confirmation"
    assert pending.affected_count == 1
    assert pending.preview_json["changes"][0]["tags"] == ["Agent"]
    assert post.version == original_version
    assert db_session.query(PostTag).filter(PostTag.post_id == post.id).count() == 0
    assert db_session.query(PostKeywordLink).filter(PostKeywordLink.post_id == post.id).count() == 0

    decide_pending_write(
        db_session,
        user_id=user.id,
        task_id=task.id,
        confirmation_id=pending.id,
        decision="approve",
    )

    db_session.refresh(post)
    assert post.summary == "审批前只生成，审批后保存。"
    assert post.version == original_version + 1
    assert db_session.query(PostTag).filter(PostTag.post_id == post.id).count() == 1
    assert db_session.query(PostKeywordLink).filter(PostKeywordLink.post_id == post.id).count() == 1
