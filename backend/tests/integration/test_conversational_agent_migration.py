"""Migration upgrade/downgrade and cascade-safety for conversation/MCP tables."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect, text

from tests.conftest import TEST_DATABASE_URL, requires_db

pytestmark = [pytest.mark.integration, requires_db]

NEW_TABLES = (
    "agent_conversations",
    "agent_messages",
    "agent_turns",
    "agent_routing_decisions",
    "mcp_connections",
    "mcp_tool_snapshots",
    "mcp_tool_grants",
)


def test_migration_head_revision_chains_from_agent_runtime() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    head = script.get_revision("head")
    assert head is not None
    assert head.revision == "0020_conversational_agent"
    assert head.down_revision == "0019_agent_runtime"


def test_upgrade_creates_all_tables_and_downgrade_removes_them() -> None:
    from alembic import command
    from alembic.config import Config
    from app.db.session import get_engine, reset_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))

    reset_engine()
    inspector = inspect(get_engine())
    for table in NEW_TABLES:
        assert inspector.has_table(table), f"{table} should exist at head"

    try:
        command.downgrade(cfg, "0019_agent_runtime")
        reset_engine()
        inspector = inspect(get_engine())
        for table in NEW_TABLES:
            assert not inspector.has_table(table), f"{table} should be gone after downgrade"
    finally:
        command.upgrade(cfg, "head")
        reset_engine()

    inspector = inspect(get_engine())
    for table in NEW_TABLES:
        assert inspector.has_table(table), f"{table} should exist again after re-upgrade"


def _make_conversation_chain(session, user_id: uuid.UUID) -> dict[str, uuid.UUID]:
    from app.models.agent_conversation import AgentConversation, AgentMessage, AgentTurn
    from app.modules.jobs import service as jobs_service

    conversation = AgentConversation(user_id=user_id, status="active", context_json={})
    session.add(conversation)
    session.flush()

    message = AgentMessage(
        conversation_id=conversation.id,
        user_id=user_id,
        role="user",
        kind="text",
        content_json={"text": "hi"},
        client_message_id=f"cascade-{uuid.uuid4()}",
    )
    session.add(message)
    session.flush()

    job = jobs_service.create_job(session, user_id=user_id, job_type="agent.conversation_turn")

    turn = AgentTurn(
        conversation_id=conversation.id,
        user_message_id=message.id,
        job_id=job.id,
        status="accepted",
    )
    session.add(turn)
    session.flush()
    session.commit()
    return {"conversation_id": conversation.id, "message_id": message.id, "turn_id": turn.id}


def test_deleting_user_cascades_conversation_message_and_turn(db_session, make_user) -> None:
    from app.models.agent_conversation import AgentConversation, AgentMessage, AgentTurn
    from app.models.foundation import User

    user = make_user()
    ids = _make_conversation_chain(db_session, user.id)

    db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    db_session.commit()
    db_session.expunge_all()

    assert db_session.get(User, user.id) is None
    assert db_session.get(AgentConversation, ids["conversation_id"]) is None
    assert db_session.get(AgentMessage, ids["message_id"]) is None
    assert db_session.get(AgentTurn, ids["turn_id"]) is None


def test_deleting_agent_task_only_nulls_turn_reference(db_session, make_user) -> None:
    """Deleting an AgentTask's own cascade chain must not delete the Turn
    run-record — only null out the reference (data-model.md Retention section)."""
    from app.models.agent import AgentTask
    from app.models.agent_conversation import AgentTurn
    from app.modules.jobs import service as jobs_service

    user = make_user()
    ids = _make_conversation_chain(db_session, user.id)

    task_job = jobs_service.create_job(db_session, user_id=user.id, job_type="agent.execute")
    task = AgentTask(
        user_id=user.id,
        job=task_job,
        request_text="test",
        intent_key="chat",
        status="pending",
        scope_json={},
    )
    db_session.add(task)
    db_session.flush()

    turn = db_session.get(AgentTurn, ids["turn_id"])
    turn.agent_task_id = task.id
    db_session.commit()

    db_session.execute(text("DELETE FROM agent_tasks WHERE id = :id"), {"id": task.id})
    db_session.commit()
    db_session.expunge_all()

    assert db_session.get(AgentTask, task.id) is None
    refreshed_turn = db_session.get(AgentTurn, ids["turn_id"])
    assert refreshed_turn is not None
    assert refreshed_turn.agent_task_id is None


def test_deleting_mcp_connection_cascades_snapshots_and_grants(db_session, make_user) -> None:
    from app.models.agent_conversation import McpConnection, McpToolGrant, McpToolSnapshot

    user = make_user()
    connection = McpConnection(
        user_id=user.id,
        config_key="example-notes",
        display_name="Example Notes",
        transport="streamable_http",
        health_status="unknown",
    )
    db_session.add(connection)
    db_session.flush()

    snapshot = McpToolSnapshot(
        connection_id=connection.id,
        tool_key="mcp.example-notes.search",
        remote_name="search",
        responsibility="search notes",
        tool_type="read",
        input_schema_json={"type": "object"},
        risk_json={},
        available=True,
        catalog_version="v1",
    )
    grant = McpToolGrant(
        user_id=user.id,
        connection_id=connection.id,
        tool_key="mcp.example-notes.search",
        allowed=True,
    )
    db_session.add_all([snapshot, grant])
    db_session.commit()

    db_session.execute(text("DELETE FROM mcp_connections WHERE id = :id"), {"id": connection.id})
    db_session.commit()
    db_session.expunge_all()

    assert db_session.get(McpConnection, connection.id) is None
    assert db_session.get(McpToolSnapshot, snapshot.id) is None
    assert db_session.get(McpToolGrant, grant.id) is None


def test_client_message_id_unique_per_user_partial_index(db_session, make_user) -> None:
    """The (user_id, client_message_id) uniqueness only applies when set — two
    messages with a NULL client_message_id must not conflict."""
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from sqlalchemy.exc import IntegrityError

    user = make_user()
    conversation = AgentConversation(user_id=user.id, status="active", context_json={})
    db_session.add(conversation)
    db_session.flush()

    db_session.add_all(
        [
            AgentMessage(
                conversation_id=conversation.id,
                user_id=user.id,
                role="assistant",
                kind="text",
                content_json={},
                client_message_id=None,
            ),
            AgentMessage(
                conversation_id=conversation.id,
                user_id=user.id,
                role="assistant",
                kind="text",
                content_json={},
                client_message_id=None,
            ),
        ]
    )
    db_session.commit()

    db_session.add(
        AgentMessage(
            conversation_id=conversation.id,
            user_id=user.id,
            role="user",
            kind="text",
            content_json={},
            client_message_id="dup-key",
        )
    )
    db_session.commit()
    db_session.add(
        AgentMessage(
            conversation_id=conversation.id,
            user_id=user.id,
            role="user",
            kind="text",
            content_json={},
            client_message_id="dup-key",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
