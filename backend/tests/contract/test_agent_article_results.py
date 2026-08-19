"""Contract for safe, interactive article results returned by the Agent."""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.contract]


def test_recent_article_result_has_owned_detail_link_and_no_body(db_session, make_user) -> None:
    from app.models.posts import Post
    from app.modules.agent.registry import ToolContext, _list_recent_posts

    owner = make_user()
    other_user = make_user()
    owned = Post(user_id=owner.id, title="我的文章", markdown="不应作为结果返回", status="private")
    db_session.add_all(
        [
            owned,
            Post(user_id=other_user.id, title="他人的文章", markdown="私有内容", status="private"),
        ]
    )
    db_session.flush()

    result = _list_recent_posts(
        ToolContext(user_id=owner.id, task_id=uuid.uuid4(), session=db_session),
        {"limit": 10},
    )

    assert result == [
        {
            "id": str(owned.id),
            "title": "我的文章",
            "link": f"/blog/{owned.id}/view",
            "category": None,
            "tags": [],
            "published_at": None,
            "updated_at": owned.updated_at.isoformat(),
            "status": "private",
        }
    ]
    assert "markdown" not in result[0]
