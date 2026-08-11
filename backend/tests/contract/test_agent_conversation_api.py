"""REST contract for conversation CRUD and message submission/listing."""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.contract]


def _login(client, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_create_list_get_conversation_contract(client, make_user, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.agent.router.execute_conversation_turn.delay",
        lambda _turn_id: None,
    )
    user = make_user()
    headers = _login(client, user.email)

    created = client.post("/api/v1/agent/conversations", headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {"id", "title", "status", "last_message_at", "created_at"}
    assert body["status"] == "active"
    assert body["title"] is None
    assert body["last_message_at"] is None

    listed = client.get("/api/v1/agent/conversations", headers=headers)
    assert listed.status_code == 200
    ids = [c["id"] for c in listed.json()]
    assert body["id"] in ids

    detail = client.get(f"/api/v1/agent/conversations/{body['id']}", headers=headers)
    assert detail.status_code == 200
    detail_body = detail.json()
    assert set(detail_body) == {
        "id",
        "title",
        "status",
        "last_message_at",
        "created_at",
        "active_turns",
    }
    assert detail_body["active_turns"] == []


def test_get_conversation_requires_csrf_free_but_ownership_scoped(
    client, make_user, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.modules.agent.router.execute_conversation_turn.delay",
        lambda _turn_id: None,
    )
    owner = make_user()
    other = make_user()
    owner_headers = _login(client, owner.email)

    created = client.post("/api/v1/agent/conversations", headers=owner_headers)
    conversation_id = created.json()["id"]

    _login(client, other.email)
    cross_user = client.get(f"/api/v1/agent/conversations/{conversation_id}")
    assert cross_user.status_code == 404

    missing = client.get(f"/api/v1/agent/conversations/{uuid.uuid4()}", headers=owner_headers)
    assert missing.status_code == 404


def test_submit_and_list_messages_contract(client, make_user, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.agent.router.execute_conversation_turn.delay",
        lambda _turn_id: None,
    )
    user = make_user()
    headers = _login(client, user.email)

    conversation = client.post("/api/v1/agent/conversations", headers=headers).json()
    conversation_id = conversation["id"]

    client_message_id = str(uuid.uuid4())
    submitted = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        headers=headers,
        json={"client_message_id": client_message_id, "text": "hi"},
    )
    assert submitted.status_code == 202
    payload = submitted.json()
    assert set(payload) == {"message", "turn"}
    assert set(payload["message"]) == {"id", "role", "kind", "content", "turn_id", "created_at"}
    assert payload["message"]["role"] == "user"
    assert payload["message"]["kind"] == "text"
    assert payload["message"]["content"] == {"text": "hi"}
    assert set(payload["turn"]) == {
        "id",
        "conversation_id",
        "status",
        "route_kind",
        "current_step",
        "agent_task_id",
        "error_message",
        "created_at",
        "finished_at",
    }
    assert payload["turn"]["conversation_id"] == conversation_id
    assert payload["turn"]["status"] == "accepted"

    # Resubmitting the same client_message_id is idempotent: same turn back.
    replay = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        headers=headers,
        json={"client_message_id": client_message_id, "text": "hi"},
    )
    assert replay.status_code == 202
    assert replay.json()["turn"]["id"] == payload["turn"]["id"]

    listed = client.get(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        headers=headers,
    )
    assert listed.status_code == 200
    page = listed.json()
    assert set(page) == {"items", "next_cursor"}
    assert len(page["items"]) == 1
    assert page["items"][0]["id"] == payload["message"]["id"]
    assert page["next_cursor"] is None


def test_submit_message_requires_csrf(client, make_user) -> None:
    user = make_user()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert login.status_code == 200

    created = client.post(
        "/api/v1/agent/conversations", headers={"X-CSRF-Token": login.json()["csrf_token"]}
    )
    conversation_id = created.json()["id"]

    # No CSRF header supplied on this unsafe POST.
    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"client_message_id": str(uuid.uuid4()), "text": "hi"},
    )
    assert response.status_code == 403


def test_submit_message_to_foreign_conversation_is_404(client, make_user) -> None:
    owner = make_user()
    other = make_user()
    owner_headers = _login(client, owner.email)
    created = client.post("/api/v1/agent/conversations", headers=owner_headers)
    conversation_id = created.json()["id"]

    other_headers = _login(client, other.email)
    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        headers=other_headers,
        json={"client_message_id": str(uuid.uuid4()), "text": "hi"},
    )
    assert response.status_code == 404


def test_message_pagination_cursor(client, make_user, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.agent.router.execute_conversation_turn.delay",
        lambda _turn_id: None,
    )
    user = make_user()
    headers = _login(client, user.email)
    conversation_id = client.post("/api/v1/agent/conversations", headers=headers).json()["id"]

    for _ in range(3):
        client.post(
            f"/api/v1/agent/conversations/{conversation_id}/messages",
            headers=headers,
            json={"client_message_id": str(uuid.uuid4()), "text": "hi"},
        )

    first_page = client.get(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        headers=headers,
        params={"limit": 2},
    )
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert len(first_body["items"]) == 2
    assert first_body["next_cursor"] is not None

    second_page = client.get(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        headers=headers,
        params={"limit": 2, "cursor": first_body["next_cursor"]},
    )
    assert second_page.status_code == 200
    second_body = second_page.json()
    assert len(second_body["items"]) == 1
    assert second_body["next_cursor"] is None
    assert {m["id"] for m in first_body["items"]} & {m["id"] for m in second_body["items"]} == (
        set()
    )
