"""Blog capture API contract: clipboard / URL / quick / blank (US1, T028).

Asserts the request/response shape of the durable capture endpoints against the
OpenAPI CaptureResult contract, including the pending-Job semantics for URL.
"""

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


def _assert_capture_shape(body, *, expect_job):
    assert set(body) == {"post", "source", "job", "warnings"}
    assert isinstance(body["warnings"], list)
    post, source = body["post"], body["source"]
    assert post["id"] and post["content_status"]
    assert source["id"] and source["source_type"] and source["status"]
    assert source["captured_at"]
    if expect_job:
        assert body["job"] is not None
        assert body["job"]["id"] and body["job"]["status"]
    else:
        assert body["job"] is None


def test_blank_capture_creates_draft(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.post("/api/v1/posts/captures/blank", json={"title": "空白"}, headers=h)
    assert r.status_code == 201
    body = r.json()
    _assert_capture_shape(body, expect_job=False)
    assert body["post"]["content_status"] == "draft"
    assert body["source"]["source_type"] == "blank"


def test_clipboard_capture_normalizes_html(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.post(
        "/api/v1/posts/captures/clipboard",
        json={"raw_content": "<h1>标题</h1><p>正文 <b>粗</b></p>", "detected_format": "html"},
        headers=h,
    )
    assert r.status_code == 201
    body = r.json()
    _assert_capture_shape(body, expect_job=False)
    assert body["source"]["status"] == "completed"
    assert "# 标题" in body["post"]["markdown"]
    assert body["source"]["original_text"]  # raw preserved


def test_clipboard_rejects_bad_format(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.post(
        "/api/v1/posts/captures/clipboard",
        json={"raw_content": "x", "detected_format": "not-real"},
        headers=h,
    )
    assert r.status_code == 422


def test_url_capture_is_durable_and_async(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.post(
        "/api/v1/posts/captures/url",
        json={"url": "https://example.com/article", "note": "读一读"},
        headers=h,
    )
    assert r.status_code == 202
    body = r.json()
    _assert_capture_shape(body, expect_job=True)
    assert body["post"]["content_status"] == "pending_parse"
    assert body["source"]["source_type"] == "url"
    assert body["source"]["status"] == "pending"
    assert body["source"]["original_url"] == "https://example.com/article"
    assert body["job"]["job_type"] == "blog.parse"


def test_url_capture_rejects_unsafe_scheme(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.post(
        "/api/v1/posts/captures/url",
        json={"url": "file:///etc/passwd"},
        headers=h,
    )
    assert r.status_code == 422


def test_quick_capture_goes_to_triage(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.post(
        "/api/v1/posts/captures/quick",
        json={"content": "记一笔"},
        headers=h,
    )
    assert r.status_code == 201
    body = r.json()
    _assert_capture_shape(body, expect_job=False)
    assert body["post"]["content_status"] == "triage"
    assert body["post"]["markdown"] == "记一笔"


def test_source_detail_readable_by_owner(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    cap = client.post(
        "/api/v1/posts/captures/quick", json={"content": "细节"}, headers=h
    ).json()
    sid = cap["source"]["id"]
    r = client.get(f"/api/v1/post-sources/{sid}", headers=h)
    assert r.status_code == 200
    assert r.json()["id"] == sid
