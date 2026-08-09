"""Independent Agent work preserves durable successes when a subset fails."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

pytestmark = [pytest.mark.integration]


def test_five_of_twenty_five_failures_produce_partial_success(
    db_session, make_user
) -> None:
    from app.models.agent import AgentRun, ExecutionRecord
    from app.models.posts import Post
    from app.modules.agent.service import create_agent_task, execute_analysis_task

    user = make_user()
    posts = [
        Post(
            user_id=user.id,
            title=f"文章 {index}",
            markdown=f"第 {index} 篇文章的原始正文，包含稳定且不可被分析任务修改的内容。",
            status="private",
        )
        for index in range(25)
    ]
    db_session.add_all(posts)
    db_session.flush()
    failed_ids = {str(post.id) for post in posts[:5]}
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="为这些文章提取标签和关键词",
        intent_key="articles.analyze",
        scope={"object_ids": [str(post.id) for post in posts]},
    )
    db_session.commit()

    def analyze(post: dict[str, str], _request_text: str) -> dict[str, object]:
        if post["id"] in failed_ids:
            raise ValueError(f"文章 {post['id']} 无法分析")
        return {
            "post_id": post["id"],
            "tags": [" Agent ", "agent", ""],
            "keywords": ["并行处理", "并行处理"],
            "summary": "已生成分析结果，尚未保存",
        }

    completed = execute_analysis_task(db_session, task.id, analyze_post=analyze)
    db_session.commit()
    db_session.refresh(completed)

    reply = json.loads(completed.result_summary or "{}")
    generated = reply["执行结果"]["已生成未保存"]
    failed = reply["执行结果"]["失败"]
    runs = list(
        db_session.scalars(
            select(AgentRun).where(
                AgentRun.task_id == task.id,
                AgentRun.parent_run_id.is_not(None),
            )
        ).all()
    )
    records = list(
        db_session.scalars(
            select(ExecutionRecord).where(ExecutionRecord.task_id == task.id)
        ).all()
    )

    assert completed.status == "partial_success"
    assert completed.job.status == "completed"
    assert len(generated) == 20
    assert len(failed) == 5
    assert {item["post_id"] for item in failed} == failed_ids
    assert all(item["reason"] for item in failed)
    assert reply["执行结果"]["已保存"] == []
    assert reply["执行结果"]["未处理"] == []
    assert len(runs) > 1
    assert all(run.agent_version.startswith("blog-agents.1:") for run in runs)
    scopes = [set(run.input_scope_json["object_ids"]) for run in runs]
    assert all(
        not left.intersection(right)
        for index, left in enumerate(scopes)
        for right in scopes[index + 1 :]
    )
    assert len(records) == 26
    assert sum(record.status == "failed" for record in records) == 5
    assert all(post.markdown.startswith("第 ") for post in posts)
