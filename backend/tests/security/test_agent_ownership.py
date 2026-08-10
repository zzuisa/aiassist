"""Agent task existence is hidden across owners."""

from __future__ import annotations

import pytest
from app.db.session import session_scope
from app.modules.agent.service import create_agent_task

pytestmark = [pytest.mark.security]


def _login(client, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200


def test_cross_user_task_access_returns_404(client, make_user) -> None:
    owner = make_user()
    other = make_user()
    with session_scope() as session:
        task = create_agent_task(
            session,
            user_id=owner.id,
            request_text="给我最近 10 篇文章",
            intent_key="articles.list_recent",
        )
        task_id = task.id

    _login(client, other.email)
    assert client.get(f"/api/v1/agent/tasks/{task_id}").status_code == 404
