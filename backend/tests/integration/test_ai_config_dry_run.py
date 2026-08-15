from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


def _login(client, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_non_writing_dry_run_creates_safe_binding(client, make_user) -> None:
    user = make_user()
    headers = _login(client, user.email)

    result = client.post(
        "/api/v1/ai-config/modules/quick_plan/dry-run",
        headers=headers,
        json={"input_text": "明天上午喝咖啡"},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "configuration_resolved"
    assert result.json()["tool_call"] is None

    bindings = client.get("/api/v1/ai-config/modules/bindings/recent")
    assert bindings.status_code == 200
    assert bindings.json()[0]["module_key"] == "quick_plan"
    assert bindings.json()[0]["run_reference"] == "dry-run"
