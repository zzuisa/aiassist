"""Safe MCP catalog diagnostics; never prints endpoints or credentials."""

from __future__ import annotations

import uuid


def issue_blog_token(email: str, days: int) -> int:
    """Print one scoped blog MCP token for an active user.

    The token is intentionally printed once for direct entry into an MCP client;
    callers must redirect/store it as a secret and must not place it in logs.
    """
    from sqlalchemy import select

    from app.db.session import session_scope
    from app.models.foundation import User
    from app.modules.blog_mcp.auth import issue_blog_mcp_token

    with session_scope() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None or user.status != "active":
            print("Active user not found.", file=__import__("sys").stderr)
            return 1
        token, expires_at = issue_blog_mcp_token(user.id, days=days)
    print(token)
    print(
        f"Token scope=blog:read expires_at={expires_at.isoformat()}",
        file=__import__("sys").stderr,
    )
    return 0


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
