from __future__ import annotations

import pytest

pytestmark = [pytest.mark.contract]


def test_mcp_manifest_contains_only_safe_v2_fields(db_session, make_user, monkeypatch) -> None:
    from app.models.agent_conversation import McpToolGrant
    from app.modules.agent.conversation_service import sync_mcp_connections
    from app.modules.agent.registry import tool_registry
    from app.services.mcp.config import ConnectionSafeMetadata
    from app.services.mcp.gateway import McpGateway

    from tests.fixtures.mcp_server import StubMcpProvider

    user = make_user()
    monkeypatch.setattr(
        "app.services.mcp.config.list_safe_mcp_metadata",
        lambda: [ConnectionSafeMetadata("notes-main", "Notes", "streamable_http", "safe.invalid")],
    )
    connection = sync_mcp_connections(
        db_session, user_id=user.id, gateway=McpGateway(StubMcpProvider())
    )[0]
    db_session.add(
        McpToolGrant(
            user_id=user.id,
            connection_id=connection.id,
            tool_key="mcp.notes-main.notes",
            allowed=True,
            allowed_operations_json=["query"],
            scope_json={},
            granted_at=connection.created_at,
        )
    )
    db_session.flush()
    entry = next(
        item
        for item in tool_registry.safe_manifest_v2(session=db_session, user_id=user.id)["tools"]
        if item["key"] == "notes-main-notes"
    )
    assert set(entry) == {
        "key",
        "source",
        "type",
        "responsibility",
        "input_schema",
        "output_schema",
        "risk",
        "required_permission",
        "available",
        "unavailable_reason",
    }
    assert "safe.invalid" not in str(entry)
