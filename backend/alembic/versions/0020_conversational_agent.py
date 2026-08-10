"""Add durable conversation, turn, routing, and MCP metadata tables.

Revision ID: 0020_conversational_agent
Revises: 0019_agent_runtime

No foreign keys into business-entity tables (posts, tasks, etc.) per
specs/008-conversational-agent-mcp/data-model.md. ``agent_turns.agent_task_id``
uses ``ON DELETE SET NULL`` so deleting an AgentTask's own cascade chain never
removes the Turn run-record; ``agent_messages``/``agent_turns``/
``agent_routing_decisions`` cascade among themselves only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_conversational_agent"
down_revision: str | None = "0019_agent_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('active','archived')",
            name=op.f("ck_agent_conversations_agent_conversation_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_agent_conversations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_conversations")),
    )
    op.create_index(
        "ix_agent_conversations_user_status_last_message",
        "agent_conversations",
        ["user_id", "status", sa.text("last_message_at DESC")],
    )

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("client_message_id", sa.String(length=120), nullable=True),
        sa.Column("reply_to_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role in ('user','assistant','system')",
            name=op.f("ck_agent_messages_agent_message_role"),
        ),
        sa.CheckConstraint(
            "kind in ('text','clarification','result','error')",
            name=op.f("ck_agent_messages_agent_message_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversations.id"],
            name=op.f("fk_agent_messages_conversation_id_agent_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_agent_messages_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_id"],
            ["agent_messages.id"],
            name=op.f("fk_agent_messages_reply_to_id_agent_messages"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_messages")),
    )
    op.create_index(
        "uq_agent_messages_user_client_message_id",
        "agent_messages",
        ["user_id", "client_message_id"],
        unique=True,
        postgresql_where=sa.text("client_message_id IS NOT NULL"),
    )
    op.create_index(
        "ix_agent_messages_conversation_created_at",
        "agent_messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "agent_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_message_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_message_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("agent_task_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("route_kind", sa.String(length=24), nullable=True),
        sa.Column("current_step", sa.String(length=120), nullable=True),
        sa.Column("retry_of_id", sa.Uuid(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('accepted','routing','waiting_clarification','executing',"
            "'waiting_confirmation','success','partial_success','failed','stalled',"
            "'cancelled')",
            name=op.f("ck_agent_turns_agent_turn_status"),
        ),
        sa.CheckConstraint(
            "route_kind is null or route_kind in "
            "('chat','capability_help','clarification','task')",
            name=op.f("ck_agent_turns_agent_turn_route_kind"),
        ),
        sa.CheckConstraint(
            "retry_count >= 0",
            name=op.f("ck_agent_turns_agent_turn_retry_count_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversations.id"],
            name=op.f("fk_agent_turns_conversation_id_agent_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_message_id"],
            ["agent_messages.id"],
            name=op.f("fk_agent_turns_user_message_id_agent_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"],
            ["agent_messages.id"],
            name=op.f("fk_agent_turns_assistant_message_id_agent_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["async_jobs.id"],
            name=op.f("fk_agent_turns_job_id_async_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_task_id"],
            ["agent_tasks.id"],
            name=op.f("fk_agent_turns_agent_task_id_agent_tasks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["retry_of_id"],
            ["agent_turns.id"],
            name=op.f("fk_agent_turns_retry_of_id_agent_turns"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_turns")),
        sa.UniqueConstraint("job_id", name="uq_agent_turns_job_id"),
    )
    op.create_index(
        "ix_agent_turns_conversation_created_at",
        "agent_turns",
        ["conversation_id", "created_at"],
    )
    op.create_index("ix_agent_turns_retry_of_id", "agent_turns", ["retry_of_id"])
    op.create_index(
        "ix_agent_turns_status_last_heartbeat",
        "agent_turns",
        ["status", "last_heartbeat_at"],
    )

    op.create_table(
        "agent_routing_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=40), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("route_kind", sa.String(length=24), nullable=False),
        sa.Column("objective", sa.String(length=500), nullable=False),
        sa.Column("operation_type", sa.String(length=24), nullable=False),
        sa.Column("target_scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("semantic_args_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidate_tools_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selected_tool", sa.String(length=160), nullable=True),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("validation_status", sa.String(length=20), nullable=False),
        sa.Column("validation_errors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "route_kind in ('chat','capability_help','clarification','task')",
            name=op.f("ck_agent_routing_decisions_agent_routing_decision_route_kind"),
        ),
        sa.CheckConstraint(
            "operation_type in ('none','query','analyze','create','update','delete',"
            "'publish','rollback','external_effect')",
            name=op.f("ck_agent_routing_decisions_agent_routing_decision_operation_type"),
        ),
        sa.CheckConstraint(
            "validation_status in ('valid','invalid')",
            name=op.f("ck_agent_routing_decisions_agent_routing_decision_validation_status"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 and confidence <= 1",
            name=op.f("ck_agent_routing_decisions_agent_routing_decision_confidence_range"),
        ),
        sa.CheckConstraint(
            "attempt >= 1",
            name=op.f("ck_agent_routing_decisions_agent_routing_decision_attempt_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["agent_turns.id"],
            name=op.f("fk_agent_routing_decisions_turn_id_agent_turns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_routing_decisions")),
        sa.UniqueConstraint(
            "turn_id", "attempt", name="uq_agent_routing_decisions_turn_attempt"
        ),
    )
    op.create_index(
        "ix_agent_routing_decisions_turn_id", "agent_routing_decisions", ["turn_id"]
    )

    op.create_table(
        "mcp_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("config_key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("transport", sa.String(length=24), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("health_status", sa.String(length=16), nullable=False),
        sa.Column("protocol_version", sa.String(length=24), nullable=True),
        sa.Column("catalog_etag", sa.String(length=120), nullable=True),
        sa.Column("catalog_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "transport in ('streamable_http')",
            name=op.f("ck_mcp_connections_mcp_connection_transport"),
        ),
        sa.CheckConstraint(
            "health_status in ('unknown','healthy','degraded','unavailable','disabled')",
            name=op.f("ck_mcp_connections_mcp_connection_health_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_mcp_connections_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_connections")),
        sa.UniqueConstraint(
            "user_id", "config_key", name="uq_mcp_connections_user_config_key"
        ),
    )
    op.create_index(
        "ix_mcp_connections_user_enabled", "mcp_connections", ["user_id", "enabled"]
    )

    op.create_table(
        "mcp_tool_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("tool_key", sa.String(length=160), nullable=False),
        sa.Column("remote_name", sa.String(length=160), nullable=False),
        sa.Column("responsibility", sa.String(length=500), nullable=False),
        sa.Column("tool_type", sa.String(length=16), nullable=False),
        sa.Column("input_schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("risk_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("unavailable_reason", sa.String(length=500), nullable=True),
        sa.Column("catalog_version", sa.String(length=64), nullable=False),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tool_type in ('read','write')",
            name=op.f("ck_mcp_tool_snapshots_mcp_tool_snapshot_type"),
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["mcp_connections.id"],
            name=op.f("fk_mcp_tool_snapshots_connection_id_mcp_connections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_tool_snapshots")),
        sa.UniqueConstraint(
            "connection_id",
            "tool_key",
            "catalog_version",
            name="uq_mcp_tool_snapshots_connection_tool_catalog",
        ),
    )
    op.create_index(
        "ix_mcp_tool_snapshots_connection_tool_key",
        "mcp_tool_snapshots",
        ["connection_id", "tool_key"],
    )

    op.create_table(
        "mcp_tool_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("tool_key", sa.String(length=160), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("allowed_operations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_mcp_tool_grants_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["mcp_connections.id"],
            name=op.f("fk_mcp_tool_grants_connection_id_mcp_connections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_tool_grants")),
        sa.UniqueConstraint(
            "user_id",
            "connection_id",
            "tool_key",
            name="uq_mcp_tool_grants_user_connection_tool",
        ),
    )
    op.create_index(
        "ix_mcp_tool_grants_user_allowed", "mcp_tool_grants", ["user_id", "allowed"]
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_tool_grants_user_allowed", table_name="mcp_tool_grants")
    op.drop_table("mcp_tool_grants")

    op.drop_index(
        "ix_mcp_tool_snapshots_connection_tool_key", table_name="mcp_tool_snapshots"
    )
    op.drop_table("mcp_tool_snapshots")

    op.drop_index("ix_mcp_connections_user_enabled", table_name="mcp_connections")
    op.drop_table("mcp_connections")

    op.drop_index(
        "ix_agent_routing_decisions_turn_id", table_name="agent_routing_decisions"
    )
    op.drop_table("agent_routing_decisions")

    op.drop_index("ix_agent_turns_status_last_heartbeat", table_name="agent_turns")
    op.drop_index("ix_agent_turns_retry_of_id", table_name="agent_turns")
    op.drop_index("ix_agent_turns_conversation_created_at", table_name="agent_turns")
    op.drop_table("agent_turns")

    op.drop_index(
        "ix_agent_messages_conversation_created_at", table_name="agent_messages"
    )
    op.drop_index(
        "uq_agent_messages_user_client_message_id", table_name="agent_messages"
    )
    op.drop_table("agent_messages")

    op.drop_index(
        "ix_agent_conversations_user_status_last_message",
        table_name="agent_conversations",
    )
    op.drop_table("agent_conversations")
