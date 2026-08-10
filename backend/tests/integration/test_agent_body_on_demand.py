"""Article bodies are available only through the explicit body-read tool."""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.integration]


def test_body_tool_reads_owned_body_while_list_tool_stays_lightweight(
    db_session, make_user
) -> None:
    from app.models.posts import Post
    from app.modules.agent.registry import ToolContext, tool_registry

    user = make_user()
    post = Post(user_id=user.id, title="文章", markdown="PRIVATE BODY", status="private")
    db_session.add(post)
    db_session.commit()
    context = ToolContext(user_id=user.id, task_id=uuid.uuid4(), session=db_session)

    listed = tool_registry.invoke("posts.list_recent", context=context, params={"limit": 10})
    body = tool_registry.invoke(
        "posts.read_body",
        context=context,
        params={"post_ids": [str(post.id)]},
    )

    assert all("markdown" not in item for item in listed)
    assert body == [{"id": str(post.id), "title": "文章", "markdown": "PRIVATE BODY"}]
