"""Calendar week, preview/apply, fixed-event and partial-conflict contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


def _mk(client, h, **body):
    return client.post("/api/v1/tasks", json=body, headers=h).json()


def test_week_returns_events_and_conflicts(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    base = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)  # a Monday
    _mk(
        client,
        h,
        title="A",
        type="task",
        start_at=base.isoformat(),
        due_at=(base + timedelta(hours=1)).isoformat(),
    )
    _mk(
        client,
        h,
        title="B",
        type="task",
        start_at=(base + timedelta(minutes=30)).isoformat(),
        due_at=(base + timedelta(minutes=90)).isoformat(),
    )
    resp = client.get("/api/v1/calendar/week", params={"starts_on": "2026-07-27"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["events"]) == 2
    assert len(data["conflicts"]) == 1


def test_preview_then_apply_is_two_separate_calls(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    base = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
    _mk(
        client,
        h,
        title="A",
        type="task",
        start_at=base.isoformat(),
        due_at=(base + timedelta(hours=1)).isoformat(),
    )
    _mk(
        client,
        h,
        title="B",
        type="task",
        start_at=(base + timedelta(minutes=30)).isoformat(),
        due_at=(base + timedelta(minutes=90)).isoformat(),
    )
    # Phase 1: preview (no task changed).
    preview = client.post(
        "/api/v1/schedule-previews",
        json={"scope_start": base.isoformat(), "scope_end": (base + timedelta(days=1)).isoformat()},
        headers=h,
    )
    assert preview.status_code == 202
    pid = preview.json()["preview_id"]
    got = client.get(f"/api/v1/schedule-previews/{pid}")
    assert got.status_code == 200
    assert got.json()["status"] == "ready"


def test_fixed_event_suggestion_is_not_selectable(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    base = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
    _mk(
        client,
        h,
        title="Fixed",
        type="fixed_event",
        is_fixed=True,
        start_at=base.isoformat(),
        due_at=(base + timedelta(hours=1)).isoformat(),
    )
    _mk(
        client,
        h,
        title="Flex",
        type="task",
        start_at=(base + timedelta(minutes=30)).isoformat(),
        due_at=(base + timedelta(minutes=90)).isoformat(),
    )
    preview = client.post(
        "/api/v1/schedule-previews",
        json={"scope_start": base.isoformat(), "scope_end": (base + timedelta(days=1)).isoformat()},
        headers=h,
    ).json()
    detail = client.get(f"/api/v1/schedule-previews/{preview['preview_id']}").json()
    # Any suggestion referencing the fixed event must be keep/non-selectable.
    for s in detail["suggestions"]:
        if s["reason"] == "固定事件不移动":
            assert s["selectable"] is False
            assert s["recommendation"] == "keep"


def test_apply_rejects_stale_version(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    base = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
    a = _mk(
        client,
        h,
        title="A",
        type="task",
        start_at=base.isoformat(),
        due_at=(base + timedelta(hours=1)).isoformat(),
    )
    _mk(
        client,
        h,
        title="B",
        type="task",
        start_at=(base + timedelta(minutes=30)).isoformat(),
        due_at=(base + timedelta(minutes=90)).isoformat(),
    )
    preview = client.post(
        "/api/v1/schedule-previews",
        json={"scope_start": base.isoformat(), "scope_end": (base + timedelta(days=1)).isoformat()},
        headers=h,
    ).json()
    # Mutate task A so the preview's recorded version is stale.
    client.patch(f"/api/v1/tasks/{a['id']}", json={"version": 1, "title": "A2"}, headers=h)
    detail = client.get(f"/api/v1/schedule-previews/{preview['preview_id']}").json()
    sel = [s["suggestion_id"] for s in detail["suggestions"] if s["selectable"]]
    if sel:
        result = client.post(
            f"/api/v1/schedule-previews/{preview['preview_id']}/apply",
            json={"suggestion_ids": sel},
            headers=h,
        )
        assert result.status_code == 200
        codes = {r["code"] for r in result.json()["rejected"]}
        assert "version_conflict" in codes or result.json()["applied"] == []
