"""Public Agent tool manifest follows the safe versioned contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

pytestmark = [pytest.mark.contract]


def _login(client, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200


def test_agent_tools_manifest_is_safe_and_schema_valid(client, make_user) -> None:
    user = make_user()
    _login(client, user.email)

    response = client.get("/api/v1/agent/tools")

    assert response.status_code == 200
    payload = response.json()
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "specs/007-self-service-agent/contracts/schemas/agent-tool-manifest.v1.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
    assert payload["schema_version"] == "agent-tool-manifest.v1"
    assert payload["tools"]
    safe_fields = {
        "name",
        "type",
        "responsibility",
        "required_permission",
        "available",
        "unavailable_reason",
        "source",
    }
    assert all(set(tool) <= safe_fields for tool in payload["tools"])
    rendered = json.dumps(payload, ensure_ascii=False).casefold()
    for forbidden in ("endpoint", "connection_string", "api_key", "authorization", "cookie"):
        assert forbidden not in rendered
