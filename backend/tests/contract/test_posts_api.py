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


# ---------------------------------------------------------------------------
# Additive-field regression (spec 005, US2 fields — T011)
#
# US2 added subtitle/summary/content_class/structured_data/etc. to Post. These
# guard that the additive fields (a) round-trip through PATCH, (b) never leak
# into the public post projection, and (c) don't break publish or the RSS feed.
# ---------------------------------------------------------------------------

_PUBLIC_POST_KEYS = {"slug", "title", "html", "excerpt", "published_at"}


def _patch_additive(client, h, post):
    return client.patch(
        f"/api/v1/posts/{post['id']}",
        json={
            "version": post["version"],
            "subtitle": "副标题",
            "summary": "一句话摘要",
            "content_class": "technical",
            "project": "个人博客",
            "structured_data": {"city": "上海"},
        },
        headers=h,
    )


def test_additive_fields_round_trip(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post = _draft(client, h)
    r = _patch_additive(client, h, post)
    assert r.status_code == 200
    updated = r.json()
    assert updated["subtitle"] == "副标题"
    assert updated["summary"] == "一句话摘要"
    assert updated["content_class"] == "technical"
    assert updated["project"] == "个人博客"
    assert updated["structured_data"] == {"city": "上海"}
    assert updated["version"] == post["version"] + 1


def test_public_post_projection_excludes_additive_fields(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post = _draft(client, h, title="公开文章")
    updated = _patch_additive(client, h, post).json()
    published = client.post(
        f"/api/v1/posts/{post['id']}/publish",
        json={"published": True, "version": updated["version"]},
        headers=h,
    ).json()
    pub = client.get(f"/api/v1/public/posts/{published['slug']}")
    assert pub.status_code == 200
    body = pub.json()
    # The public contract stays exactly the stable set — additive/private fields
    # (subtitle, summary, structured_data, project) must not leak.
    assert set(body) == _PUBLIC_POST_KEYS
    assert body["title"] == "公开文章"


def test_rss_still_lists_post_with_additive_fields(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post = _draft(client, h, title="含元数据的 RSS 文章")
    updated = _patch_additive(client, h, post).json()
    client.post(
        f"/api/v1/posts/{post['id']}/publish",
        json={"published": True, "version": updated["version"]},
        headers=h,
    )
    rss = client.get("/api/v1/public/rss.xml")
    assert rss.status_code == 200
    assert "含元数据的 RSS 文章" in rss.text
    # Private additive content is never serialized into the public feed.
    assert "一句话摘要" not in rss.text
    assert "上海" not in rss.text
