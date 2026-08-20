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
            "'success','partial_success','failed','cancelled')",
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


class AgentExecutionPlan(Base, TimestampMixin):
    """One durable, bounded dependency graph for an AgentTask."""

    __tablename__ = "agent_execution_plans"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_turns.id", ondelete="CASCADE")
    )
    schema_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="agent-task-plan.v1"
    )
    objective: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="planning")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_summary: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    graph_thread_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    graph_run_id: Mapped[str | None] = mapped_column(String(128))
    runtime_state: Mapped[str] = mapped_column(String(24), nullable=False, default="checkpointed")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status in ('planning','pending','running','waiting_user','success',"
            "'partial_success','failed','stalled','cancelled')",
            name="agent_execution_plan_status",
        ),
        CheckConstraint("version >= 1", name="agent_execution_plan_version_positive"),
        CheckConstraint(
            "runtime_state in ('checkpointed','running','interrupted','completed','failed')",
            name="agent_execution_plan_runtime_state",
        ),
        CheckConstraint("step_count >= 1 and step_count <= 12", name="agent_plan_step_count"),
        UniqueConstraint("task_id", name="uq_agent_execution_plans_task_id"),
        UniqueConstraint("turn_id", name="uq_agent_execution_plans_turn_id"),
        Index("ix_agent_execution_plans_user_created", "user_id", "created_at"),
        Index("ix_agent_execution_plans_status_updated", "status", "updated_at"),
    )


class AgentPlanStep(Base, TimestampMixin):
    """One independently schedulable unit in a durable execution plan."""

    __tablename__ = "agent_plan_steps"

    id: Mapped[uuid.UUID] = uuid_pk()
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_execution_plans.id", ondelete="CASCADE"), nullable=False
    )
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    responsibility: Mapped[str] = mapped_column(String(300), nullable=False)
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(24), nullable=False)
    arguments_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_source: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_output: Mapped[str] = mapped_column(String(300), nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    progress_current: Mapped[int | None] = mapped_column(Integer)
    progress_total: Mapped[int | None] = mapped_column(Integer)
    stage_label: Mapped[str | None] = mapped_column(String(120))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_summary: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status in ('pending','queued','running','waiting_confirmation','success',"
            "'partial_success','failed','blocked','skipped','stalled','cancelled')",
            name="agent_plan_step_status",
        ),
        CheckConstraint("position >= 1", name="agent_plan_step_position_positive"),
        CheckConstraint("attempt_count >= 0 and attempt_count <= 2", name="agent_plan_attempts"),
        UniqueConstraint("plan_id", "step_key", name="uq_agent_plan_steps_plan_key"),
        UniqueConstraint("plan_id", "position", name="uq_agent_plan_steps_plan_position"),
        Index("ix_agent_plan_steps_plan_status", "plan_id", "status"),
    )


class AgentStepDependency(Base):
    __tablename__ = "agent_step_dependencies"

    id: Mapped[uuid.UUID] = uuid_pk()
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_execution_plans.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_plan_steps.id", ondelete="CASCADE"), nullable=False
    )
    depends_on_step_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_plan_steps.id", ondelete="CASCADE"), nullable=False
    )
    accepted_statuses_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=lambda: ["success", "partial_success"]
    )

    __table_args__ = (
        CheckConstraint("step_id <> depends_on_step_id", name="agent_step_dependency_no_self"),
        UniqueConstraint("step_id", "depends_on_step_id", name="uq_agent_step_dependency_edge"),
        Index("ix_agent_step_dependencies_plan", "plan_id"),
    )


class AgentStepArtifact(Base):
    __tablename__ = "agent_step_artifacts"

    id: Mapped[uuid.UUID] = uuid_pk()
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_execution_plans.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_plan_steps.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[dict | list] = mapped_column(JSONB, nullable=False)
    object_scope_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_agent_step_artifacts_plan_step", "plan_id", "step_id"),)


class AgentStepAttempt(Base):
    __tablename__ = "agent_step_attempts"

    id: Mapped[uuid.UUID] = uuid_pk()
    step_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_plan_steps.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint(
            "attempt_number >= 1 and attempt_number <= 2", name="agent_step_attempt_no"
        ),
        CheckConstraint(
            "status in ('running','success','failed')", name="agent_step_attempt_status"
        ),
        UniqueConstraint("step_id", "attempt_number", name="uq_agent_step_attempt_number"),
        UniqueConstraint("idempotency_key", name="uq_agent_step_attempt_idempotency"),
    )
