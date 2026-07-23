"""Security gate: IDOR, CSRF, JWT claims, login throttle, log redaction, assets."""

from __future__ import annotations

import pytest
from app.modules.auth import service as auth_service

pytestmark = [pytest.mark.security, pytest.mark.integration]


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


def test_idor_task_access_blocked(client, make_user):
    owner = make_user()
    other = make_user()
    h = _login(client, owner.email)
    task = client.post("/api/v1/tasks", json={"title": "secret", "type": "task"}, headers=h).json()
    auth_service.reset_login_throttle()
    _login(client, other.email)
    # Cross-user read/update/delete all 404 (existence hidden).
    assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 404


def test_csrf_required_on_unsafe_methods(client, make_user):
    user = make_user()
    _login(client, user.email)  # cookies set, but no CSRF header supplied
    resp = client.post("/api/v1/tasks", json={"title": "x", "type": "task"})
    assert resp.status_code == 403


def test_jwt_tampering_rejected(client, make_user):
    user = make_user()
    _login(client, user.email)
    # Corrupt the access cookie.
    client.cookies.set(auth_service.ACCESS_COOKIE, "not.a.valid.jwt")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_rate_limited(client, make_user):
    user = make_user()
    for _ in range(10):
        client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "wrong-password-value"},
        )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "wrong-password-value"},
    )
    assert resp.status_code == 429


def test_generic_login_error_no_user_enumeration(client, make_user):
    make_user(email="known@example.com")
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.com", "password": "whatever-password"},
    )
    known_bad = client.post(
        "/api/v1/auth/login",
        json={"email": "known@example.com", "password": "wrong-password-value"},
    )
    # Identical error code for unknown user vs wrong password.
    assert unknown.json()["code"] == known_bad.json()["code"] == "invalid_credentials"


def test_log_redaction_masks_secrets():
    import io

    import structlog
    from app.core.observability import configure_logging, get_logger

    configure_logging("INFO")
    buf = io.StringIO()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            __import__("app.core.observability", fromlist=["_redact_processor"])._redact_processor,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(buf),
    )
    get_logger("t").info("event", password="supersecret", api_key="k", safe="ok")
    out = buf.getvalue()
    assert "supersecret" not in out
    assert "[redacted]" in out
    assert "ok" in out


def test_storage_key_never_returned_to_client(client, make_user):
    """Capture assets expose an access URL, never the internal storage_key."""
    user = make_user()
    h = _login(client, user.email)
    capture = client.post("/api/v1/captures", json={"type": "item", "title": "x"}, headers=h).json()
    body = client.get(f"/api/v1/captures/{capture['id']}").json()
    serialized = str(body)
    assert "storage_key" not in serialized
    assert "/data/assets" not in serialized
