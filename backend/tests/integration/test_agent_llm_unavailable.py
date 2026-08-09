"""Provider failure never mutates/fabricates content and remains retryable."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


def test_dependency_failure_preserves_article_and_returns_no_fake_result(
    db_session, make_user
) -> None:
    import json

    from app.models.posts import Post
    from app.modules.agent.service import create_agent_task, execute_analysis_task
    from app.modules.jobs import service as jobs_service
    from app.services.llm.base import LLMError

    user = make_user()
    post = Post(user_id=user.id, title="原始标题", markdown="原始正文", status="private")
    db_session.add(post)
    db_session.flush()
    post_id = post.id
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="分析这篇文章并提取关键词",
        intent_key="articles.analyze",
        scope={"object_ids": [str(post_id)]},
    )
    db_session.commit()

    def unavailable(_post: dict[str, str], _request_text: str) -> None:
        raise LLMError("provider_unavailable", "LLM gateway unavailable")

    failed = execute_analysis_task(db_session, task.id, analyze_post=unavailable)
    db_session.commit()
    db_session.expire_all()
    preserved = db_session.get(Post, post_id)
    failed = db_session.get(type(task), task.id)
    assert failed is not None
    first_reply = json.loads(failed.result_summary or "{}")

    assert failed.status == "failed"
    assert failed.job.status == "failed"
    assert failed.job.error_retryable is True
    assert first_reply["执行结果"]["已生成未保存"] == []
    assert first_reply["执行结果"]["失败"][0]["post_id"] == str(post_id)
    assert preserved is not None
    assert (preserved.title, preserved.markdown) == ("原始标题", "原始正文")

    jobs_service.retry_job(db_session, failed.job)

    def recovered(post_data: dict[str, str], _request_text: str) -> dict[str, object]:
        return {
            "post_id": post_data["id"],
            "tags": ["恢复"],
            "keywords": ["真实结果"],
            "summary": "依赖恢复后的真实结果",
        }

    retried = execute_analysis_task(db_session, task.id, analyze_post=recovered)
    db_session.commit()
    db_session.refresh(retried)
    db_session.refresh(preserved)

    retry_reply = json.loads(retried.result_summary or "{}")
    assert retried.status == "success"
    assert retried.job.status == "completed"
    assert retry_reply["执行结果"]["已生成未保存"][0]["keywords"] == ["真实结果"]
    assert (preserved.title, preserved.markdown) == ("原始标题", "原始正文")
