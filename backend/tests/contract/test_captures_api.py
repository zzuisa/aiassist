"""Capture API: save-first, provenance display, user-over-AI, convert, ownership."""

from __future__ import annotations

import io

import pytest
from app.modules.auth import service as auth_service
from PIL import Image

pytestmark = [pytest.mark.contract, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _tmp_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_ROOT", str(tmp_path))
    from app.core.config import reload_settings
    from app.services.storage.providers.local import reset_storage

    reload_settings()
    reset_storage()
    auth_service.reset_login_throttle()
    yield
    reset_storage()


def _login(client, email):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(out, format="PNG")
    return out.getvalue()


def _upload(client, h) -> str:
    data = _png()
    session = client.post(
        "/api/v1/uploads",
        json={
            "purpose": "capture",
            "filename": "k.png",
            "media_type": "image/png",
            "byte_size": len(data),
        },
        headers=h,
    ).json()
    client.put(f"/api/v1/uploads/{session['id']}/content", content=data, headers=h)
    client.post(f"/api/v1/uploads/{session['id']}/complete", headers=h)
    return session["id"]


def test_create_capture_saves_before_processing(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    upload_id = _upload(client, h)
    resp = client.post(
        "/api/v1/captures",
        json={"type": "item", "title": "厨房剪刀", "upload_ids": [upload_id]},
        headers=h,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["processing_status"] in ("pending", "processing")
    assert body["private"] is True
    assert len(body["assets"]) == 1


def test_user_value_shown_with_user_provenance(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    resp = client.post(
        "/api/v1/captures",
        json={"type": "item", "title": "我的标题"},
        headers=h,
    ).json()
    assert resp["fields"]["title"]["source"] == "user"
    assert resp["fields"]["title"]["value"] == "我的标题"


def test_update_does_not_lose_user_value(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    created = client.post(
        "/api/v1/captures", json={"type": "item", "title": "原标题"}, headers=h
    ).json()
    updated = client.patch(
        f"/api/v1/captures/{created['id']}",
        json={"version": created["version"], "brand": "我的品牌"},
        headers=h,
    ).json()
    assert updated["fields"]["brand"]["source"] == "user"
    assert updated["fields"]["title"]["value"] == "原标题"


def test_convert_capture_to_task(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    created = client.post(
        "/api/v1/captures", json={"type": "item", "title": "待办来源"}, headers=h
    ).json()
    resp = client.post(
        f"/api/v1/captures/{created['id']}/convert",
        json={"target_type": "task"},
        headers=h,
    )
    assert resp.status_code == 201
    assert resp.json()["type"] == "task"


def test_cross_user_capture_not_readable(client, make_user):
    owner = make_user()
    other = make_user()
    h = _login(client, owner.email)
    created = client.post(
        "/api/v1/captures", json={"type": "item", "title": "私密"}, headers=h
    ).json()
    auth_service.reset_login_throttle()
    _login(client, other.email)
    assert client.get(f"/api/v1/captures/{created['id']}").status_code == 404
