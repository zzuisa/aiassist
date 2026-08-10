"""A follow-up pronoun inherits only the prior owned object scope."""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.integration]


def _login(client, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_previous_task_scope_is_inherited_without_expanding_to_all_posts(
    client,
    make_user,
    monkeypatch,
) -> None:
    from app.db.session import session_scope
    from app.models.agent import AgentTask
    from app.models.posts import Post
    from app.modules.agent.service import create_agent_task

    user = make_user()
    headers = _login(client, user.email)
    with session_scope() as session:
        posts = [
            Post(user_id=user.id, title=f"范围文章 {index}", markdown="正文", status="private")
            for index in range(4)
        ]
        session.add_all(posts)
        session.flush()
        selected = posts[:2]
        previous = create_agent_task(
            session,
            user_id=user.id,
            request_text="给我最近 2 篇文章",
            intent_key="articles.list_recent",
            scope={
                "object_ids": [str(post.id) for post in selected],
                "object_versions": {str(post.id): post.version for post in selected},
                "query_conditions": {"limit": 2},
                "query_range": {"returned": 2, "limit": 2},
                "sort": "updated_desc",
                "confirmed_operations": [{"operation": "read", "status": "confirmed"}],
                "pending_write_ids": [],
                "completed_object_ids": [],
                "failed_object_ids": [],
                "valid": True,
            },
        )
        previous_id = previous.id
        expected_ids = [str(post.id) for post in selected]

    monkeypatch.setattr("app.modules.agent.router.execute_task.delay", lambda _task_id: None)
    response = client.post(
        "/api/v1/agent/tasks",
        headers=headers,
        json={
            "request_text": "给这些文章提取标签",
            "previous_task_id": str(previous_id),
        },
    )
    assert response.status_code == 202

    with session_scope() as session:
        follow_up = session.get(AgentTask, uuid.UUID(response.json()["task_id"]))
        assert follow_up is not None
        assert follow_up.scope_json["object_ids"] == expected_ids
        assert follow_up.scope_json["query_conditions"] == {"limit": 2}
        assert follow_up.scope_json["sort"] == "updated_desc"
        assert follow_up.scope_json["previous_task_id"] == str(previous_id)
        assert follow_up.scope_json["valid"] is True


def test_previous_task_must_belong_to_current_user(client, make_user, monkeypatch) -> None:
    from app.db.session import session_scope
    from app.modules.agent.service import create_agent_task

    owner = make_user(email="scope-owner@example.com")
    other = make_user(email="scope-other@example.com")
    with session_scope() as session:
        previous = create_agent_task(
            session,
            user_id=owner.id,
            request_text="给我最近 1 篇文章",
            intent_key="articles.list_recent",
            scope={"object_ids": []},
        )
        previous_id = previous.id

    headers = _login(client, other.email)
    monkeypatch.setattr("app.modules.agent.router.execute_task.delay", lambda _task_id: None)
    response = client.post(
        "/api/v1/agent/tasks",
        headers=headers,
        json={"request_text": "处理这些文章", "previous_task_id": str(previous_id)},
    )
    assert response.status_code == 404
