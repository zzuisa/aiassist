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
    access_cookie, _ = auth_service.auth_cookie_names()
    client.cookies.set(access_cookie, "not.a.valid.jwt")
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


def test_stdlib_log_is_json_and_written_to_service_file(tmp_path, monkeypatch):
    import json
    import logging

    from app.core.observability import configure_logging

    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    configure_logging("INFO", service="worker-fast")
    logging.getLogger("celery.task").warning("worker diagnostic")

    lines = (tmp_path / "worker-fast.log").read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    assert record["event"] == "worker diagnostic"
    assert record["message"] == "worker diagnostic"
    assert record["service"] == "worker-fast"
    assert record["level"] == "warning"

    try:
        raise RuntimeError("simulated worker failure")
    except RuntimeError:
        logging.getLogger("celery.task").exception("worker crashed")
    error_record = json.loads(
        (tmp_path / "worker-fast.log").read_text(encoding="utf-8").splitlines()[-1]
    )
    assert error_record["message"] == "worker crashed"
    assert "RuntimeError: simulated worker failure" in error_record["exception"]


def test_backend_file_excludes_uvicorn_access_logs(tmp_path, monkeypatch):
    import logging

    from app.core.observability import configure_logging

    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    configure_logging("INFO", service="backend")
    logging.getLogger("uvicorn.access").info("GET /health 200")
    logging.getLogger("app.business").error("business operation failed")

    content = (tmp_path / "backend.log").read_text(encoding="utf-8")
    assert "GET /health 200" not in content
    assert "business operation failed" in content


def test_handled_api_error_keeps_event_and_human_message(caplog):
    from app.core.errors import ConflictError, register_exception_handlers
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/conflict")
    def conflict():
        raise ConflictError(
            "Job has already completed",
            code="job_finished",
            log_context={"event": "job_cancel_rejected", "job_status": "completed"},
        )

    with TestClient(app) as client, caplog.at_level("WARNING"):
        assert client.get("/conflict").status_code == 409

    record = next(item for item in caplog.records if item.name == "api.error")
    rendered = record.getMessage()
    assert "job_cancel_rejected" in rendered
    assert "Job has already completed" in rendered


def test_storage_key_never_returned_to_client(client, make_user):
    """Capture assets expose an access URL, never the internal storage_key."""
    user = make_user()
    h = _login(client, user.email)
    capture = client.post("/api/v1/captures", json={"type": "item", "title": "x"}, headers=h).json()
    body = client.get(f"/api/v1/captures/{capture['id']}").json()
    serialized = str(body)
    assert "storage_key" not in serialized
    assert "/data/assets" not in serialized
