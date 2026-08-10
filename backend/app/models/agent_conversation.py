"""Durable models for the conversational Agent layer and MCP tool gateway.

These tables extend the self-service Agent runtime (``app/models/agent.py``)
with a persistent conversation/message/turn history and provider-neutral MCP
connection metadata. Per data-model.md there are deliberately NO foreign keys
into business-entity tables (posts, tasks, etc.) — only conversation/message/
turn/routing-decision rows cascade among themselves, and Turn only cascades
its own run-record, never the linked AgentTask/business object. MCP secrets
(endpoints, tokens, connection strings) never appear here — only the opaque
``config_key`` that the read-only secrets file resolves.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk

CONVERSATION_STATUSES = ("active", "archived")
MESSAGE_ROLES = ("user", "assistant", "system")
MESSAGE_KINDS = ("text", "clarification", "result", "error")
TURN_STATUSES = (
    "accepted",
    "routing",
    "waiting_clarification",
    "executing",
    "waiting_confirmation",
    "success",
    "partial_success",
    "failed",
    "stalled",
    "cancelled",
)
TURN_TERMINAL_STATUSES = ("success", "partial_success", "failed", "stalled", "cancelled")
ROUTE_KINDS = ("chat", "capability_help", "clarification", "task")
ROUTE_OPERATION_TYPES = (
    "none",
    "query",
    "analyze",
    "create",
    "update",
    "delete",
    "publish",
    "rollback",
    "external_effect",
)
ROUTE_VALIDATION_STATUSES = ("valid", "invalid")
MCP_TRANSPORTS = ("streamable_http",)
MCP_HEALTH_STATUSES = ("unknown", "healthy", "degraded", "unavailable", "disabled")
MCP_TOOL_TYPES = ("read", "write")


class AgentConversation(Base, TimestampMixin):
    """One persistent, owned conversation thread."""

    __tablename__ = "agent_conversations"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    context_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status in ('active','archived')",
            name="agent_conversation_status",
        ),
        Index(
            "ix_agent_conversations_user_status_last_message",
            "user_id",
            "status",
            text("last_message_at DESC"),
        ),
    )


class AgentMessage(Base):
    """One user, assistant, or system-status message within a conversation."""

    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    content_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    client_message_id: Mapped[str | None] = mapped_column(String(120))
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("role in ('user','assistant','system')", name="agent_message_role"),
        CheckConstraint(
            "kind in ('text','clarification','result','error')",
            name="agent_message_kind",
        ),
        Index(
            "uq_agent_messages_user_client_message_id",
            "user_id",
            "client_message_id",
            unique=True,
            postgresql_where=text("client_message_id IS NOT NULL"),
        ),
        Index(
            "ix_agent_messages_conversation_created_at",
            "conversation_id",
            "created_at",
        ),
    )


class AgentTurn(Base):
    """The lifecycle of one user message from acceptance to reply completion."""

    __tablename__ = "agent_turns"

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="CASCADE"), nullable=False
    )
    assistant_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="SET NULL")
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("async_jobs.id", ondelete="CASCADE"), nullable=False
    )
    # Deliberately no FK cascade coupling: deleting an AgentTask (which itself
    # cascades from its own job) must not delete this Turn's run-record; the
    # column is nulled out instead. See data-model.md Retention and Deletion.
    agent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="accepted")
    route_kind: Mapped[str | None] = mapped_column(String(24))
    current_step: Mapped[str | None] = mapped_column(String(120))
    retry_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_turns.id", ondelete="SET NULL")
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status in ('accepted','routing','waiting_clarification','executing',"
            "'waiting_confirmation','success','partial_success','failed','stalled',"
            "'cancelled')",
            name="agent_turn_status",
        ),
        CheckConstraint(
            "route_kind is null or route_kind in "
            "('chat','capability_help','clarification','task')",
            name="agent_turn_route_kind",
        ),
        CheckConstraint("retry_count >= 0", name="agent_turn_retry_count_nonnegative"),
        UniqueConstraint("job_id", name="uq_agent_turns_job_id"),
        Index("ix_agent_turns_conversation_created_at", "conversation_id", "created_at"),
        Index("ix_agent_turns_retry_of_id", "retry_of_id"),
        Index("ix_agent_turns_status_last_heartbeat", "status", "last_heartbeat_at"),
    )


class AgentRoutingDecision(Base):
    """One structured, auditable routing fact for a Turn (no hidden reasoning)."""

    __tablename__ = "agent_routing_decisions"

    id: Mapped[uuid.UUID] = uuid_pk()
    turn_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_turns.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    route_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    objective: Mapped[str] = mapped_column(String(500), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_scope_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    semantic_args_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    candidate_tools_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    selected_tool: Mapped[str | None] = mapped_column(String(160))
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="valid")
    validation_errors_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "route_kind in ('chat','capability_help','clarification','task')",
            name="agent_routing_decision_route_kind",
        ),
        CheckConstraint(
            "operation_type in ('none','query','analyze','create','update','delete',"
            "'publish','rollback','external_effect')",
            name="agent_routing_decision_operation_type",
        ),
        CheckConstraint(
            "validation_status in ('valid','invalid')",
            name="agent_routing_decision_validation_status",
        ),
        CheckConstraint(
            "confidence >= 0 and confidence <= 1",
            name="agent_routing_decision_confidence_range",
        ),
        CheckConstraint("attempt >= 1", name="agent_routing_decision_attempt_positive"),
        UniqueConstraint("turn_id", "attempt", name="uq_agent_routing_decisions_turn_attempt"),
        Index("ix_agent_routing_decisions_turn_id", "turn_id"),
    )


class McpConnection(Base, TimestampMixin):
    """Non-secret registration for one operator-configured MCP server."""

    __tablename__ = "mcp_connections"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Opaque key into the read-only secrets file. NEVER a URL, token, or
    # connection string — see app/services/mcp/config.py.
    config_key: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    transport: Mapped[str] = mapped_column(String(24), nullable=False, default="streamable_http")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    health_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    protocol_version: Mapped[str | None] = mapped_column(String(24))
    catalog_etag: Mapped[str | None] = mapped_column(String(120))
    catalog_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint("transport in ('streamable_http')", name="mcp_connection_transport"),
        CheckConstraint(
            "health_status in ('unknown','healthy','degraded','unavailable','disabled')",
            name="mcp_connection_health_status",
        ),
        UniqueConstraint("user_id", "config_key", name="uq_mcp_connections_user_config_key"),
        Index("ix_mcp_connections_user_enabled", "user_id", "enabled"),
    )


class McpToolSnapshot(Base):
    """The most recently discovered safe tool description for one connection."""

    __tablename__ = "mcp_tool_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mcp_connections.id", ondelete="CASCADE"), nullable=False
    )
    tool_key: Mapped[str] = mapped_column(String(160), nullable=False)
    remote_name: Mapped[str] = mapped_column(String(160), nullable=False)
    responsibility: Mapped[str] = mapped_column(String(500), nullable=False)
    tool_type: Mapped[str] = mapped_column(String(16), nullable=False)
    input_schema_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_schema_json: Mapped[dict | None] = mapped_column(JSONB)
    risk_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    unavailable_reason: Mapped[str | None] = mapped_column(String(500))
    catalog_version: Mapped[str] = mapped_column(String(64), nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("tool_type in ('read','write')", name="mcp_tool_snapshot_type"),
        UniqueConstraint(
            "connection_id",
            "tool_key",
            "catalog_version",
            name="uq_mcp_tool_snapshots_connection_tool_catalog",
        ),
        Index("ix_mcp_tool_snapshots_connection_tool_key", "connection_id", "tool_key"),
    )


class McpToolGrant(Base, TimestampMixin):
    """A user's minimal-permission grant for one specific MCP tool."""

    __tablename__ = "mcp_tool_grants"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mcp_connections.id", ondelete="CASCADE"), nullable=False
    )
    tool_key: Mapped[str] = mapped_column(String(160), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allowed_operations_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    scope_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "connection_id",
            "tool_key",
            name="uq_mcp_tool_grants_user_connection_tool",
        ),
        Index("ix_mcp_tool_grants_user_allowed", "user_id", "allowed"),
    )
