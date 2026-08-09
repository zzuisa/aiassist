"""Taxonomy statistics use the existing aggregate service."""

from __future__ import annotations

import json

import pytest
from app.models.blog import PostCategoryProfile
from app.models.foundation import Category
from app.modules.agent.service import create_agent_task, execute_query_task

pytestmark = [pytest.mark.integration]


def test_category_count_uses_taxonomy_aggregate_not_article_listing(
    db_session, make_user, monkeypatch
) -> None:
    user = make_user()
    for name in ("技术", "生活"):
        category = Category(user_id=user.id, name=name, kind="post")
        db_session.add(category)
        db_session.flush()
        db_session.add(
            PostCategoryProfile(category_id=category.id, user_id=user.id, enabled=True)
        )
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="当前有多少类别的文章",
        intent_key="taxonomy.categories",
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.modules.posts.query_service.list_posts",
        lambda *_args, **_kwargs: pytest.fail("category aggregation must not list posts"),
    )
    execute_query_task(db_session, task.id)
    db_session.commit()
    db_session.refresh(task)

    payload = json.loads(task.result_summary or "{}")
    assert payload["处理结果"]["category_count"] == 2
    assert {item["name"] for item in payload["处理结果"]["categories"]} == {"技术", "生活"}
