from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]


def test_revoked_or_missing_grant_is_not_available(db_session, make_user, monkeypatch) -> None:
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
    sync_mcp_connections(db_session, user_id=user.id, gateway=McpGateway(StubMcpProvider()))
    entry = next(
        item
        for item in tool_registry.safe_manifest_v2(session=db_session, user_id=user.id)["tools"]
        if item["key"] == "mcp.notes-main.notes"
    )
    assert entry["available"] is False
    assert "safe.invalid" not in str(entry)
