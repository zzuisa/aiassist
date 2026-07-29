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
        "127.0.0.1",       # loopback
        "0.0.0.0",         # unspecified
        "10.0.0.1",        # private A
        "172.16.5.4",      # private B
        "192.168.1.1",     # private C
        "169.254.169.254", # link-local (cloud metadata)
        "::1",             # IPv6 loopback
        "fc00::1",         # IPv6 unique-local
        "fe80::1",         # IPv6 link-local
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

from tests.conftest import requires_db  # noqa: E402

from app.modules.auth import service as auth_service  # noqa: E402


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
    cap = client.post(
        "/api/v1/posts/captures/quick", json={"content": "无快照"}, headers=h
    ).json()
    source_id = cap["source"]["id"]
    resp = client.get(f"/api/v1/post-sources/{source_id}/snapshot-access", headers=h)
    assert resp.status_code == 404  # no private key leaked when no snapshot
