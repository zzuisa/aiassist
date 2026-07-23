"""Settings API: get/patch, timezone validation, password change, isolation."""

from __future__ import annotations

import pytest
from app.modules.auth import service as auth_service

pytestmark = [pytest.mark.contract, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _reset():
    auth_service.reset_login_throttle()
    yield


def _login(client, email):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_get_settings_includes_dependencies(client, make_user):
    user = make_user()
    _login(client, user.email)
    resp = client.get("/api/v1/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == user.email
    assert "mail" in body["dependencies"]
    assert body["dependencies"]["storage"]["state"] == "ready"


def test_patch_timezone_valid(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    resp = client.patch("/api/v1/settings", json={"timezone": "Asia/Shanghai"}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["user"]["timezone"] == "Asia/Shanghai"


def test_patch_timezone_invalid_rejected(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    resp = client.patch("/api/v1/settings", json={"timezone": "Mars/Phobos"}, headers=h)
    assert resp.status_code == 422


def test_notification_preferences_strict(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    resp = client.patch(
        "/api/v1/settings",
        json={"notification_preferences": {"in_app_enabled": True, "surprise": 1}},
        headers=h,
    )
    assert resp.status_code == 422


def test_password_change_revokes_other_sessions(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    resp = client.post(
        "/api/v1/settings/password",
        json={
            "current_password": "correct horse battery staple",
            "new_password": "a-brand-new-password-123",
        },
        headers=h,
    )
    assert resp.status_code == 204
    # The old refresh session was revoked.
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_password_change_wrong_current_rejected(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    resp = client.post(
        "/api/v1/settings/password",
        json={"current_password": "wrong-password-value", "new_password": "another-valid-pass-123"},
        headers=h,
    )
    assert resp.status_code == 401


def test_settings_requires_auth(client):
    assert client.get("/api/v1/settings").status_code == 401
