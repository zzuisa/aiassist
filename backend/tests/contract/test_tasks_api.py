"""Task CRUD contract: validation, optimistic version, completion, ownership."""

from __future__ import annotations

import pytest
from app.modules.auth import service as auth_service

pytestmark = [pytest.mark.contract, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _reset_throttle():
    auth_service.reset_login_throttle()
    yield


def _login(client, email: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200
    return resp.json()["csrf_token"]


def _headers(csrf: str) -> dict:
    return {"X-CSRF-Token": csrf}


def test_create_requires_csrf(client, make_user):
    user = make_user()
    _login(client, user.email)
    resp = client.post("/api/v1/tasks", json={"title": "x", "type": "task"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "csrf_failed"


def test_create_and_get_task(client, make_user):
    user = make_user()
    csrf = _login(client, user.email)
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "买菜", "type": "task", "priority": 2},
        headers=_headers(csrf),
    )
    assert resp.status_code == 201
    task = resp.json()
    assert task["title"] == "买菜"
    assert task["version"] == 1
    got = client.get(f"/api/v1/tasks/{task['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == task["id"]


def test_create_validation_rejects_empty_title(client, make_user):
    user = make_user()
    csrf = _login(client, user.email)
    resp = client.post("/api/v1/tasks", json={"title": "", "type": "task"}, headers=_headers(csrf))
    assert resp.status_code == 422


def test_fixed_event_is_not_ai_adjustable(client, make_user):
    user = make_user()
    csrf = _login(client, user.email)
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "牙医", "type": "fixed_event", "is_fixed": True, "is_ai_adjustable": True},
        headers=_headers(csrf),
    )
    assert resp.status_code == 201
    assert resp.json()["is_ai_adjustable"] is False


def test_optimistic_version_conflict(client, make_user):
    user = make_user()
    csrf = _login(client, user.email)
    created = client.post(
        "/api/v1/tasks", json={"title": "a", "type": "task"}, headers=_headers(csrf)
    ).json()
    # First update succeeds (version 1 -> 2).
    r1 = client.patch(
        f"/api/v1/tasks/{created['id']}",
        json={"version": 1, "title": "b"},
        headers=_headers(csrf),
    )
    assert r1.status_code == 200
    assert r1.json()["version"] == 2
    # Second update with stale version conflicts.
    r2 = client.patch(
        f"/api/v1/tasks/{created['id']}",
        json={"version": 1, "title": "c"},
        headers=_headers(csrf),
    )
    assert r2.status_code == 409
    assert r2.json()["code"] == "version_conflict"


def test_complete_and_delete(client, make_user):
    user = make_user()
    csrf = _login(client, user.email)
    created = client.post(
        "/api/v1/tasks", json={"title": "done me", "type": "task"}, headers=_headers(csrf)
    ).json()
    completed = client.post(
        f"/api/v1/tasks/{created['id']}/complete",
        json={"version": 1, "actual_minutes": 25},
        headers=_headers(csrf),
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["actual_minutes"] == 25

    deleted = client.delete(f"/api/v1/tasks/{created['id']}", headers=_headers(csrf))
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/tasks/{created['id']}").status_code == 404


def test_cross_user_task_is_not_readable(client, make_user):
    owner = make_user()
    other = make_user()
    csrf = _login(client, owner.email)
    task = client.post(
        "/api/v1/tasks", json={"title": "secret", "type": "task"}, headers=_headers(csrf)
    ).json()
    # Switch identity.
    auth_service.reset_login_throttle()
    _login(client, other.email)
    resp = client.get(f"/api/v1/tasks/{task['id']}")
    assert resp.status_code == 404
