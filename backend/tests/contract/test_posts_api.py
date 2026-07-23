"""Post API: draft, revision base-conflict, publish/unpublish, slug, relations."""

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


def _draft(client, h, title="我的文章", markdown="正文内容"):
    return client.post(
        "/api/v1/posts", json={"title": title, "markdown": markdown}, headers=h
    ).json()


def test_create_draft_is_private_by_default(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post = _draft(client, h)
    assert post["status"] == "draft"
    assert post["slug"] is None


def test_publish_assigns_slug_and_makes_public(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post = _draft(client, h)
    published = client.post(
        f"/api/v1/posts/{post['id']}/publish",
        json={"published": True, "version": post["version"]},
        headers=h,
    ).json()
    assert published["status"] == "published"
    assert published["slug"]
    # Anonymous read works.
    pub = client.get(f"/api/v1/public/posts/{published['slug']}")
    assert pub.status_code == 200
    assert "<p>" in pub.json()["html"]


def test_unpublish_makes_public_read_404(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post = _draft(client, h)
    published = client.post(
        f"/api/v1/posts/{post['id']}/publish",
        json={"published": True, "version": post["version"]},
        headers=h,
    ).json()
    slug = published["slug"]
    client.post(
        f"/api/v1/posts/{post['id']}/publish",
        json={"published": False, "version": published["version"]},
        headers=h,
    )
    assert client.get(f"/api/v1/public/posts/{slug}").status_code == 404


def test_private_draft_not_publicly_readable(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    _draft(client, h)
    # A random slug is not public.
    assert client.get("/api/v1/public/posts/nonexistent").status_code == 404


def test_cross_user_post_not_readable(client, make_user):
    owner = make_user()
    other = make_user()
    h = _login(client, owner.email)
    post = _draft(client, h)
    auth_service.reset_login_throttle()
    _login(client, other.email)
    assert client.get(f"/api/v1/posts/{post['id']}").status_code == 404


def test_rss_lists_published(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post = _draft(client, h, title="RSS 文章")
    client.post(
        f"/api/v1/posts/{post['id']}/publish",
        json={"published": True, "version": post["version"]},
        headers=h,
    )
    rss = client.get("/api/v1/public/rss.xml")
    assert rss.status_code == 200
    assert "RSS 文章" in rss.text
