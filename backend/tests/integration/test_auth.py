"""Authentication: login, refresh rotation, reuse detection, CSRF, isolation."""

from __future__ import annotations

import pytest
from app.modules.auth import service as auth_service
from app.modules.auth.service import ACCESS_COOKIE, REFRESH_COOKIE

pytestmark = [pytest.mark.integration]


@pytest.fixture(autouse=True)
def _reset_throttle():
    auth_service.reset_login_throttle()
    yield
    auth_service.reset_login_throttle()


def _login(client, email: str, password: str = "correct horse battery staple"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_login_sets_httponly_cookies_and_csrf(client, make_user):
    user = make_user()
    resp = _login(client, user.email)
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == user.email
    assert body["csrf_token"]
    cookies = resp.headers.get_list("set-cookie")
    joined = " ".join(cookies)
    assert ACCESS_COOKIE in joined
    assert REFRESH_COOKIE in joined
    assert "HttpOnly" in joined


def test_login_wrong_password_generic_error(client, make_user):
    user = make_user()
    resp = _login(client, user.email, password="wrong-password-value")
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_credentials"


def test_login_unknown_user_same_generic_error(client, make_user):
    make_user()
    resp = _login(client, "nobody@example.com")
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_credentials"


def test_me_requires_auth(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user(client, make_user):
    user = make_user()
    _login(client, user.email)
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == user.email


def test_refresh_rotates_and_old_token_reuse_revokes_family(client, make_user):
    user = make_user()
    _login(client, user.email)
    old_refresh = client.cookies.get(REFRESH_COOKIE)

    # First refresh rotates successfully.
    r1 = client.post("/api/v1/auth/refresh")
    assert r1.status_code == 204
    new_refresh = client.cookies.get(REFRESH_COOKIE)
    assert new_refresh != old_refresh

    # Replaying the OLD refresh token must fail and revoke the family.
    client.cookies.set(REFRESH_COOKIE, old_refresh)
    reuse = client.post("/api/v1/auth/refresh")
    assert reuse.status_code == 401
    assert reuse.json()["code"] == "refresh_reused"

    # Even the previously-valid new token is now revoked.
    client.cookies.set(REFRESH_COOKIE, new_refresh)
    after = client.post("/api/v1/auth/refresh")
    assert after.status_code == 401


def test_logout_clears_cookies_and_revokes(client, make_user):
    user = make_user()
    _login(client, user.email)
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    # Refresh after logout is rejected.
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 401


def test_login_rate_limited(client, make_user):
    user = make_user()
    for _ in range(10):
        _login(client, user.email, password="bad-password-here")
    resp = _login(client, user.email, password="bad-password-here")
    assert resp.status_code == 429


def test_cross_user_isolation_current_user(client, make_user):
    a = make_user()
    b = make_user()
    _login(client, a.email)
    me = client.get("/api/v1/auth/me").json()
    assert me["email"] == a.email
    assert me["email"] != b.email
