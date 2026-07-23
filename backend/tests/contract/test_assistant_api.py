"""Assistant API contract: run/status/action endpoints and card structure."""

from __future__ import annotations

import pytest
from app.modules.assistant import service as assistant_service
from app.modules.auth import service as auth_service

pytestmark = [pytest.mark.contract, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _reset():
    auth_service.reset_login_throttle()
    assistant_service.clear_runs()
    yield
    assistant_service.clear_runs()


def _login(client, email):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_run_returns_cards_and_grounded_refs(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    client.post("/api/v1/tasks", json={"title": "灵活任务", "type": "task"}, headers=h)
    resp = client.post("/api/v1/assistant/runs", json={"intent": "plan_today"}, headers=h)
    assert resp.status_code == 202
    body = resp.json()
    assert "cards" in body
    assert "grounded_refs" in body
    # Card actions must not leak internal (_-prefixed) fields.
    for card in body["cards"]:
        for action in card["actions"]:
            assert not any(k.startswith("_") for k in action)


def test_no_result_intent_is_honest(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    resp = client.post("/api/v1/assistant/runs", json={"intent": "plan_today"}, headers=h).json()
    assert resp["cards"][0]["id"] == "no_result"


def test_apply_action_via_api(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    task = client.post(
        "/api/v1/tasks", json={"title": "灵活任务", "type": "task"}, headers=h
    ).json()
    run = client.post("/api/v1/assistant/runs", json={"intent": "plan_today"}, headers=h).json()
    action_id = f"reschedule:{task['id']}"
    resp = client.post(f"/api/v1/assistant/runs/{run['id']}/actions/{action_id}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["applied"] == action_id


def test_invalid_intent_rejected(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    resp = client.post("/api/v1/assistant/runs", json={"intent": "hack"}, headers=h)
    assert resp.status_code == 422
