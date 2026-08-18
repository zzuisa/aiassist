"""Add durable collaborative Agent execution plans."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_collaborative_agent_plans"
down_revision: str | None = "0022_ai_config_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_execution_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=True),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("objective", sa.String(500), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("step_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_retryable", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status in ('planning','pending','running','waiting_user','success','partial_success','failed','stalled','cancelled')", name="agent_execution_plan_status"),
        sa.CheckConstraint("version >= 1", name="agent_execution_plan_version_positive"),
        sa.CheckConstraint("step_count >= 1 and step_count <= 12", name="agent_plan_step_count"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["agent_turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_agent_execution_plans_task_id"),
        sa.UniqueConstraint("turn_id", name="uq_agent_execution_plans_turn_id"),
    )
    op.create_index("ix_agent_execution_plans_user_created", "agent_execution_plans", ["user_id", "created_at"])
    op.create_index("ix_agent_execution_plans_status_updated", "agent_execution_plans", ["status", "updated_at"])
    op.create_table(
        "agent_plan_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("step_key", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("responsibility", sa.String(300), nullable=False),
        sa.Column("agent_key", sa.String(64), nullable=False),
        sa.Column("agent_name", sa.String(120), nullable=False),
        sa.Column("agent_version", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(160), nullable=False),
        sa.Column("operation_type", sa.String(24), nullable=False),
        sa.Column("arguments_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_source", sa.String(32), nullable=False),
        sa.Column("expected_output", sa.String(300), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress_current", sa.Integer(), nullable=True),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("stage_label", sa.String(120), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_retryable", sa.Boolean(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status in ('pending','queued','running','waiting_confirmation','success','partial_success','failed','blocked','skipped','stalled','cancelled')", name="agent_plan_step_status"),
        sa.CheckConstraint("position >= 1", name="agent_plan_step_position_positive"),
        sa.CheckConstraint("attempt_count >= 0 and attempt_count <= 2", name="agent_plan_attempts"),
        sa.ForeignKeyConstraint(["plan_id"], ["agent_execution_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "step_key", name="uq_agent_plan_steps_plan_key"),
        sa.UniqueConstraint("plan_id", "position", name="uq_agent_plan_steps_plan_position"),
    )
    op.create_index("ix_agent_plan_steps_plan_status", "agent_plan_steps", ["plan_id", "status"])
    op.create_table(
        "agent_step_dependencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("depends_on_step_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_statuses_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("step_id <> depends_on_step_id", name="agent_step_dependency_no_self"),
        sa.ForeignKeyConstraint(["plan_id"], ["agent_execution_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["agent_plan_steps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["depends_on_step_id"], ["agent_plan_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("step_id", "depends_on_step_id", name="uq_agent_step_dependency_edge"),
    )
    op.create_index("ix_agent_step_dependencies_plan", "agent_step_dependencies", ["plan_id"])
    op.create_table(
        "agent_step_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(40), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("object_scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["agent_execution_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["agent_plan_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_step_artifacts_plan_step", "agent_step_artifacts", ["plan_id", "step_id"])
    op.create_table(
        "agent_step_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_retryable", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint("attempt_number >= 1 and attempt_number <= 2", name="agent_step_attempt_no"),
        sa.CheckConstraint("status in ('running','success','failed')", name="agent_step_attempt_status"),
        sa.ForeignKeyConstraint(["step_id"], ["agent_plan_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("step_id", "attempt_number", name="uq_agent_step_attempt_number"),
        sa.UniqueConstraint("idempotency_key", name="uq_agent_step_attempt_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("agent_step_attempts")
    op.drop_index("ix_agent_step_artifacts_plan_step", table_name="agent_step_artifacts")
    op.drop_table("agent_step_artifacts")
    op.drop_index("ix_agent_step_dependencies_plan", table_name="agent_step_dependencies")
    op.drop_table("agent_step_dependencies")
    op.drop_index("ix_agent_plan_steps_plan_status", table_name="agent_plan_steps")
    op.drop_table("agent_plan_steps")
    op.drop_index("ix_agent_execution_plans_status_updated", table_name="agent_execution_plans")
    op.drop_index("ix_agent_execution_plans_user_created", table_name="agent_execution_plans")
    op.drop_table("agent_execution_plans")
