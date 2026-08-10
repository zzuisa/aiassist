"""Changed or deleted prior objects force an explained scope refresh."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


def test_stale_prior_scope_is_requeried_and_explained(db_session, make_user) -> None:
    from app.models.posts import Post
    from app.modules.agent.service import create_agent_task, inherit_conversation_scope

    user = make_user()
    posts = [
        Post(user_id=user.id, title=f"刷新文章 {index}", markdown="正文", status="private")
        for index in range(3)
    ]
    db_session.add_all(posts)
    db_session.flush()
    previous = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="给我最近 2 篇文章",
        intent_key="articles.list_recent",
        scope={
            "object_ids": [str(posts[0].id), str(posts[1].id)],
            "object_versions": {str(posts[0].id): 1, str(posts[1].id): 1},
            "query_conditions": {"limit": 2},
            "query_range": {"returned": 2, "limit": 2},
            "sort": "updated_desc",
            "valid": True,
        },
    )
    posts[0].version = 2
    db_session.flush()

    scope = inherit_conversation_scope(
        db_session,
        user_id=user.id,
        previous=previous,
        request_text="给这些文章提取标签",
    )

    assert scope["valid"] is True
    assert scope["scope_refreshed"] is True
    assert scope["refresh_notice"]
    assert scope["query_conditions"] == {"limit": 2}
    assert len(scope["object_ids"]) == 2
    assert set(scope["object_versions"]) == set(scope["object_ids"])
