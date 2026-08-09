"""REST contract for creating and reading Agent tasks."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.contract]


def _login(client, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_create_and_get_agent_task_contract(client, make_user, monkeypatch) -> None:
    user = make_user()
    headers = _login(client, user.email)
    monkeypatch.setattr(
        "app.modules.agent.router.execute_task.delay",
        lambda _task_id: None,
    )

    created = client.post(
        "/api/v1/agent/tasks",
        headers=headers,
        json={"request_text": "给我最近 10 篇文章"},
    )

    assert created.status_code == 202
    body = created.json()
    assert set(body) == {
        "task_id",
        "job_id",
        "request_text",
        "intent_key",
        "status",
        "result_summary",
        "created_at",
        "finished_at",
    }
    assert body["request_text"] == "给我最近 10 篇文章"
    assert body["intent_key"] == "articles.list_recent"
    assert body["status"] == "pending"

    detail = client.get(f"/api/v1/agent/tasks/{body['task_id']}")
    assert detail.status_code == 200
    assert detail.json()["task_id"] == body["task_id"]
    assert detail.json()["runs"] == []
