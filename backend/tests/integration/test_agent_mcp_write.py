from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


def test_mcp_write_waits_for_confirmation_then_invokes_once(db_session, make_user, monkeypatch) -> None:
    from app.models.agent import PendingWrite
    from app.models.agent_conversation import McpToolGrant
    from app.modules.agent.conversation_service import _execute_mcp_task, sync_mcp_connections
    from app.modules.agent.service import create_agent_task, decide_pending_write
    from app.services.mcp.config import ConnectionSafeMetadata
    from app.services.mcp.gateway import McpGateway

    from tests.fixtures.mcp_server import StubMcpProvider

    user = make_user()
    provider = StubMcpProvider(tool_type="write")
    monkeypatch.setattr("app.services.mcp.config.list_safe_mcp_metadata", lambda: [ConnectionSafeMetadata("notes-main", "Notes", "streamable_http", "safe.invalid")])
    connection = sync_mcp_connections(db_session, user_id=user.id, gateway=McpGateway(provider))[0]
    db_session.add(McpToolGrant(user_id=user.id, connection_id=connection.id, tool_key="mcp.notes-main.notes", allowed=True, allowed_operations_json=["update"], scope_json={}, granted_at=connection.created_at))
    task = create_agent_task(db_session, user_id=user.id, request_text="保存外部笔记", intent_key="mcp.invoke")
    db_session.flush()
    _execute_mcp_task(db_session, task=task, tool_name="mcp.notes-main.notes", arguments={"title": "safe"}, requires_confirmation=True)
    pending = db_session.query(PendingWrite).filter_by(task_id=task.id).one()
    assert provider.calls == []
    decide_pending_write(db_session, user_id=user.id, task_id=task.id, confirmation_id=pending.id, decision="approve")
    assert len(provider.calls) == 1

