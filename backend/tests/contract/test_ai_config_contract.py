from __future__ import annotations

import pytest

pytestmark = [pytest.mark.contract]


def _login(client, email: str) -> dict[str, str]:
    from app.modules.auth import service as auth_service

    auth_service.reset_login_throttle()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_ai_config_versions_are_owned_and_activatable(client, make_user) -> None:
    owner = make_user()
    other = make_user()
    owner_headers = _login(client, owner.email)

    prompt = client.post(
        "/api/v1/ai-config/modules/conversation_route/prompt-versions",
        headers=owner_headers,
        json={"instruction": "根据语义选择一个已授权工具。"},
    )
    assert prompt.status_code == 201
    skill = client.post(
        "/api/v1/ai-config/modules/conversation_route/skill-versions",
        headers=owner_headers,
        json={
            "name": "文章查询",
            "instruction": "未指定数量时使用默认值。",
            "parameter_defaults": {"posts.list_recent": {"limit": 12}},
        },
    )
    assert skill.status_code == 201
    activated = client.post(
        "/api/v1/ai-config/modules/conversation_route/activate",
        headers=owner_headers,
        json={
            "prompt_version_id": prompt.json()["id"],
            "skill_version_id": skill.json()["id"],
        },
    )
    assert activated.status_code == 200

    _login(client, other.email)
    isolated = client.get("/api/v1/ai-config/modules/conversation_route")
    assert isolated.status_code == 200
    assert isolated.json()["prompt_versions"] == []
    assert isolated.json()["skill_versions"] == []

    _login(client, owner.email)
    detail = client.get("/api/v1/ai-config/modules/conversation_route").json()
    assert detail["active_prompt_version_id"] == prompt.json()["id"]
    assert detail["active_skill_version_id"] == skill.json()["id"]
    assert len(detail["prompt_versions"]) == 1
    assert len(detail["skill_versions"]) == 1


def test_ai_config_rejects_unregistered_skill_tool(client, make_user) -> None:
    user = make_user()
    headers = _login(client, user.email)
    response = client.post(
        "/api/v1/ai-config/modules/conversation_route/skill-versions",
        headers=headers,
        json={
            "name": "越权配置",
            "instruction": "调用未授权工具。",
            "parameter_defaults": {"posts.delete": {}},
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_skill_tool_defaults"
