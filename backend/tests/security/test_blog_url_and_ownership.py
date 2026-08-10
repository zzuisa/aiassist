"""URL SSRF defence + cross-user ownership for blog capture (US1, T031).

The SSRF cases are pure-function (no DB); ownership cases exercise the API with
two users to prove one user can never read another's source.
"""

from __future__ import annotations

import pytest
from app.modules.posts import url_extractor as ux

pytestmark = [pytest.mark.security]


# --------------------------------------------------------------- SSRF (no DB)


@pytest.mark.parametrize(
    "url,code",
    [
        ("file:///etc/passwd", "scheme_not_allowed"),
        ("ftp://example.com/x", "scheme_not_allowed"),
        ("gopher://example.com", "scheme_not_allowed"),
        ("http://user:pass@example.com/", "credentials_in_url"),
        ("http://:pass@example.com/", "credentials_in_url"),
    ],
)
def test_canonicalize_rejects_unsafe_urls(url, code):
    with pytest.raises(ux.UrlSecurityError) as exc:
        ux.canonicalize_url(url)
    assert exc.value.code == code


def test_canonicalize_strips_fragment_and_lowercases_scheme_and_host():
    out = ux.canonicalize_url("HTTP://Example.com/a/b?q=1#frag")
    # Scheme and host are canonicalized to lower-case; fragment is dropped.
    assert out.startswith("http://example.com/a/b?q=1")
    assert "#frag" not in out


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",  # loopback
        "0.0.0.0",  # noqa: S104 - deliberately rejected unspecified address
        "10.0.0.1",  # private A
        "172.16.5.4",  # private B
        "192.168.1.1",  # private C
        "169.254.169.254",  # link-local (cloud metadata)
        "::1",  # IPv6 loopback
        "fc00::1",  # IPv6 unique-local
        "fe80::1",  # IPv6 link-local
    ],
)
def test_private_and_reserved_ips_are_blocked(host):
    with pytest.raises(ux.UrlSecurityError) as exc:
        ux.assert_host_is_public(host)
    assert exc.value.code == "ip_not_public"


def test_ipv4_mapped_ipv6_localhost_blocked():
    with pytest.raises(ux.UrlSecurityError) as exc:
        ux.assert_host_is_public("::ffff:127.0.0.1")
    assert exc.value.code == "ip_not_public"


def test_unresolvable_host_reports_dns_failure():
    with pytest.raises(ux.UrlSecurityError) as exc:
        ux.assert_host_is_public("nonexistent-host.invalid-tld-xyz.test")
    assert exc.value.code == "dns_failure"


# ------------------------------------------------------------- ownership (DB)

from app.modules.auth import service as auth_service  # noqa: E402

from tests.conftest import requires_db  # noqa: E402


def _login(client, email):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@requires_db
def test_cross_user_cannot_read_source(client, make_user):
    owner = make_user()
    other = make_user()
    h = _login(client, owner.email)
    cap = client.post(
        "/api/v1/posts/captures/quick",
        json={"content": "私密内容"},
        headers=h,
    ).json()
    source_id = cap["source"]["id"]

    auth_service.reset_login_throttle()
    ho = _login(client, other.email)
    resp = client.get(f"/api/v1/post-sources/{source_id}", headers=ho)
    assert resp.status_code == 404  # never leak another user's source


@requires_db
def test_snapshot_access_404_without_snapshot(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    cap = client.post("/api/v1/posts/captures/quick", json={"content": "无快照"}, headers=h).json()
    source_id = cap["source"]["id"]
    resp = client.get(f"/api/v1/post-sources/{source_id}/snapshot-access", headers=h)
    assert resp.status_code == 404  # no private key leaked when no snapshot


# --------------------------------------------------- AI candidate isolation (US4)


def _seed_candidate(user_id):
    """Seed a post + AI run + candidate for *user_id*; returns (post_id, cand_id)."""
    import uuid as _uuid

    from app.db.session import session_scope
    from app.models.blog import BlogSkill, BlogSkillDefault, BlogSkillVersion
    from app.modules.posts import ai_service, service

    config = {
        "schema_version": "blog-skill-config.v1",
        "applicable_content_classes": ["essay"],
        "applicable_content_type_ids": [],
        "processing_goal": "improve",
        "content_rules": [],
        "title_rules": [],
        "summary_rules": [],
        "body_structure": [],
        "taxonomy_rules": [],
        "keyword_rules": [],
        "prohibitions": ["no invention"],
        "field_policies": {"title": "allow_overwrite"},
        "output_fields": ["title"],
        "output_schema": "blog-optimization.v1",
        "validation_rules": [],
        "recommended_model": "m",
        "max_content_chars": 200000,
        "long_content_strategy": "reject",
    }
    with session_scope() as s:
        skill = BlogSkill(id=_uuid.uuid4(), user_id=user_id, name="s", enabled=True)
        s.add(skill)
        s.flush()
        v = BlogSkillVersion(
            id=_uuid.uuid4(),
            user_id=user_id,
            skill_id=skill.id,
            version_number=1,
            config_json=config,
            schema_version="blog-skill-config.v1",
            recommended_model="m",
            max_content_chars=200000,
            long_content_strategy="reject",
        )
        s.add(v)
        s.flush()
        skill.current_version_id = v.id
        s.add(
            BlogSkillDefault(
                id=_uuid.uuid4(),
                user_id=user_id,
                scope_type="global",
                scope_key="*",
                skill_id=skill.id,
            )
        )
        s.flush()
        post = service.create_post(s, user_id, title="标题", markdown="正文")
        s.flush()
        _job, run, _dup = ai_service.submit_optimization(
            s,
            user_id,
            post.id,
            post_version=post.version,
            optimization_type="full",
        )
        candidate = ai_service.save_candidate(
            s,
            run,
            candidate_markdown="AI正文",
            field_diff={
                "title": {"from": "标题", "to": "AI标题", "classification": "allow_overwrite"}
            },
            validation={"outcome": "complete"},
            outcome="complete",
        )
        return str(post.id), str(candidate.id)


@requires_db
def test_other_user_cannot_read_candidate(client, make_user):
    owner = make_user()
    other = make_user()
    _post_id, cand_id = _seed_candidate(owner.id)
    ho = _login(client, other.email)
    assert client.get(f"/api/v1/blog/ai/candidates/{cand_id}", headers=ho).status_code == 404


@requires_db
def test_other_user_cannot_decide_candidate(client, make_user):
    owner = make_user()
    other = make_user()
    _post_id, cand_id = _seed_candidate(owner.id)
    ho = _login(client, other.email)
    r = client.post(
        f"/api/v1/blog/ai/candidates/{cand_id}/decide",
        json={"post_version": 1, "action": "reject"},
        headers=ho,
    )
    assert r.status_code == 404  # never mutate another user's candidate


@requires_db
def test_other_user_cannot_list_candidates(client, make_user):
    owner = make_user()
    other = make_user()
    post_id, _cand_id = _seed_candidate(owner.id)
    ho = _login(client, other.email)
    # The post itself is owned by owner → 404 for other on the nested list.
    assert client.get(f"/api/v1/posts/{post_id}/candidates", headers=ho).status_code == 404


# --------------------------------------------------- Skill isolation (US5, T100)


def _skill_config():
    return {
        "schema_version": "blog-skill-config.v1",
        "applicable_content_classes": ["essay"],
        "applicable_content_type_ids": [],
        "processing_goal": "g",
        "content_rules": [],
        "title_rules": [],
        "summary_rules": [],
        "body_structure": [],
        "taxonomy_rules": [],
        "keyword_rules": [],
        "prohibitions": ["p"],
        "field_policies": {"title": "allow_overwrite"},
        "output_fields": ["title"],
        "output_schema": "blog-optimization.v1",
        "validation_rules": [],
        "recommended_model": "m",
        "max_content_chars": 200000,
        "long_content_strategy": "reject",
    }


@requires_db
def test_other_user_cannot_read_or_edit_skill(client, make_user):
    owner = make_user()
    other = make_user()
    ho = _login(client, owner.email)
    sid = client.post(
        "/api/v1/blog/skills", json={"name": "私有", "config": _skill_config()}, headers=ho
    ).json()["id"]

    auth_service.reset_login_throttle()
    hx = _login(client, other.email)
    assert client.get(f"/api/v1/blog/skills/{sid}", headers=hx).status_code == 404
    assert client.get(f"/api/v1/blog/skills/{sid}/versions", headers=hx).status_code == 404
    assert (
        client.patch(f"/api/v1/blog/skills/{sid}", json={"name": "篡改"}, headers=hx).status_code
        == 404
    )
    # Cannot point one's own default at another user's skill.
    assert (
        client.put(
            "/api/v1/blog/skills/defaults",
            json={"scope_type": "global", "scope_key": "*", "skill_id": sid},
            headers=hx,
        ).status_code
        == 404
    )
