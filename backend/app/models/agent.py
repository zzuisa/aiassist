"""Durable runtime models for self-service Agent tasks.

The runtime owns task history only. Business objects such as posts are recorded
as UUID values inside JSON payloads and deliberately have no foreign keys here,
so clearing completed jobs can never delete user content.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_pk
from app.models.foundation import AsyncJob


class AgentTask(Base, TimestampMixin):
    """One natural-language request paired one-to-one with an async job."""

    __tablename__ = "agent_tasks"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("async_jobs.id", ondelete="CASCADE"), nullable=False
    )
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    intent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    scope_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result_summary: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[AsyncJob] = relationship()

    __table_args__ = (
        CheckConstraint(
            "status in ('pending','running','waiting_confirmation',"
            "'success','partial_success','failed')",
            name="agent_task_status",
        ),
        UniqueConstraint("job_id", name="uq_agent_tasks_job_id"),
        Index("ix_agent_tasks_user_created_at", "user_id", "created_at"),
    )


class AgentRun(Base):
    """One bound Agent configuration executing within a task."""

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False
    )
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE")
    )
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    responsibility: Mapped[str] = mapped_column(Text, nullable=False)
    current_task: Mapped[str] = mapped_column(Text, nullable=False)
    input_scope_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    allowed_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    expected_output: Mapped[str | None] = mapped_column(Text)
    allow_write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    current_tool: Mapped[str | None] = mapped_column(String(120))
    progress_current: Mapped[int | None] = mapped_column(Integer)
    progress_total: Mapped[int | None] = mapped_column(Integer)
    stage_label: Mapped[str | None] = mapped_column(String(120))
    result_summary: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status in ('pending','running','waiting_confirmation','success',"
            "'partial_success','failed','skipped')",
            name="agent_run_status",
        ),
        CheckConstraint(
            "progress_current is null or progress_current >= 0",
            name="agent_run_progress_current_nonnegative",
        ),
        CheckConstraint(
            "progress_total is null or progress_total >= 0",
            name="agent_run_progress_total_nonnegative",
        ),
        Index("ix_agent_runs_task_started_at", "task_id", "started_at"),
        Index("ix_agent_runs_parent_run_id", "parent_run_id"),
    )


class ExecutionRecord(Base):
    """One desensitized audit record for a tool, API, or child-Agent call."""

    __tablename__ = "agent_execution_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE")
    )
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    step_label: Mapped[str] = mapped_column(String(200), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    params_digest_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint(
            "operation_type in ('query','analyze','create','update','delete','publish','rollback')",
            name="agent_execution_operation_type",
        ),
        CheckConstraint(
            "status in ('success','failed','skipped')",
            name="agent_execution_status",
        ),
        CheckConstraint(
            "duration_ms is null or duration_ms >= 0",
            name="agent_execution_duration_nonnegative",
        ),
        Index("ix_agent_execution_records_task_id_id", "task_id", "id"),
    )


class PendingWrite(Base):
    """A proposed business mutation that cannot run before explicit approval."""

    __tablename__ = "agent_pending_writes"

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE")
    )
    operation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    targets_json: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    preview_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    affected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reversible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    high_risk: Mapped[bool] = mapped_column(Boolean, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "operation_type in ('query','analyze','create','update','delete','publish','rollback')",
            name="agent_pending_write_operation_type",
        ),
        CheckConstraint(
            "decision in ('pending','approved','rejected','expired')",
            name="agent_pending_write_decision",
        ),
        CheckConstraint("affected_count >= 0", name="agent_pending_write_affected_nonnegative"),
        Index("ix_agent_pending_writes_task_decision", "task_id", "decision"),
    )
