"""List queries return lightweight metadata without reading article bodies."""

from __future__ import annotations

import json

import pytest
from app.models.agent import ExecutionRecord
from app.models.posts import Post
from app.modules.agent.service import create_agent_task, execute_query_task
from sqlalchemy import select

pytestmark = [pytest.mark.integration]


def test_recent_articles_query_never_records_body_analysis(db_session, make_user) -> None:
    user = make_user()
    for index in range(12):
        db_session.add(
            Post(
                user_id=user.id,
                title=f"文章 {index:02d}",
                markdown=f"PRIVATE BODY SENTINEL {index}",
                status="private",
            )
        )
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="给我最近 10 篇文章",
        intent_key="articles.list_recent",
    )
    db_session.commit()

    execute_query_task(db_session, task.id)
    db_session.commit()
    db_session.refresh(task)

    records = list(
        db_session.scalars(
            select(ExecutionRecord).where(ExecutionRecord.task_id == task.id)
        )
    )
    assert records
    assert all(record.operation_type != "analyze" for record in records)
    rendered = task.result_summary or ""
    assert "PRIVATE BODY SENTINEL" not in rendered
    payload = json.loads(rendered)
    assert len(payload["处理结果"]) == 10
    assert all("markdown" not in item and "body" not in item for item in payload["处理结果"])
    assert all(set(item) <= {"id", "title", "link", "category", "tags", "published_at", "updated_at", "status"} for item in payload["处理结果"])
