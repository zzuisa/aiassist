"""Legacy Assistant endpoints remain compatible over durable Agent tasks."""

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


def test_legacy_run_get_and_action_survive_memory_reset(client, make_user) -> None:
    from app.modules.assistant import service as assistant_service

    user = make_user()
    headers = _login(client, user.email)
    task = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"title": "兼容任务", "type": "task"},
    ).json()
    created = client.post(
        "/api/v1/assistant/runs",
        headers=headers,
        json={"intent": "plan_today"},
    )
    assert created.status_code == 202
    run = created.json()
    assistant_service.clear_runs()

    fetched = client.get(f"/api/v1/assistant/runs/{run['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == run

    action_id = f"reschedule:{task['id']}"
    applied = client.post(
        f"/api/v1/assistant/runs/{run['id']}/actions/{action_id}",
        headers=headers,
    )
    assert applied.status_code == 200
    assert applied.json()["applied"] == action_id
