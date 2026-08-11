from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


def test_authorized_read_returns_actual_result_and_audit(db_session, make_user, monkeypatch) -> None:
    from app.models.agent import ExecutionRecord
    from app.models.agent_conversation import McpToolGrant
    from app.modules.agent.conversation_service import _execute_mcp_task, sync_mcp_connections
    from app.modules.agent.service import create_agent_task
    from app.services.mcp.config import ConnectionSafeMetadata
    from app.services.mcp.gateway import McpGateway

    from tests.fixtures.mcp_server import StubMcpProvider

    user = make_user()
    provider = StubMcpProvider()
    monkeypatch.setattr("app.services.mcp.config.list_safe_mcp_metadata", lambda: [ConnectionSafeMetadata("notes-main", "Notes", "streamable_http", "safe.invalid")])
    connection = sync_mcp_connections(db_session, user_id=user.id, gateway=McpGateway(provider))[0]
    db_session.add(McpToolGrant(user_id=user.id, connection_id=connection.id, tool_key="mcp.notes-main.notes", allowed=True, allowed_operations_json=["query"], scope_json={}, granted_at=connection.created_at))
    task = create_agent_task(db_session, user_id=user.id, request_text="查外部笔记", intent_key="mcp.invoke")
    db_session.flush()
    _execute_mcp_task(db_session, task=task, tool_name="mcp.notes-main.notes", arguments={}, requires_confirmation=False)
    assert task.status == "success"
    assert "真实测试结果" in task.result_summary
    assert db_session.query(ExecutionRecord).filter_by(task_id=task.id).count() == 1
    assert provider.calls[0][3]

