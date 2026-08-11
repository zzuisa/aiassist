"""Safe MCP catalog diagnostics; never prints endpoints or credentials."""

from __future__ import annotations

import uuid


def diagnose_mcp(user_id: str) -> int:
    from app.db.session import session_scope
    from app.modules.agent.conversation_service import sync_mcp_connections
    from app.modules.agent.registry import tool_registry

    parsed_user_id = uuid.UUID(user_id)
    with session_scope() as session:
        connections = sync_mcp_connections(session, user_id=parsed_user_id)
        manifest = tool_registry.safe_manifest_v2(session=session, user_id=parsed_user_id)
        for connection in connections:
            print(
                f"{connection.config_key}: {connection.display_name} "
                f"status={connection.health_status} error={connection.last_error_code or '-'}"
            )
        visible = [item for item in manifest["tools"] if item["source"] == "mcp"]
        print(f"MCP tools visible: {len(visible)}")
    return 0
