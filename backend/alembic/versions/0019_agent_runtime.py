"""Add durable self-service Agent runtime tables.

Revision ID: 0019_agent_runtime
Revises: 0018_blog_wordcloud_index
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_agent_runtime"
down_revision: str | None = "0018_blog_wordcloud_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("intent_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "scope_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
            "status in ('pending','running','waiting_confirmation',"
            "'success','partial_success','failed')",
            name=op.f("ck_agent_tasks_agent_task_status"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["async_jobs.id"],
            name=op.f("fk_agent_tasks_job_id_async_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_agent_tasks_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_tasks")),
        sa.UniqueConstraint("job_id", name="uq_agent_tasks_job_id"),
    )
    op.create_index(
        "ix_agent_tasks_user_created_at",
        "agent_tasks",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("parent_run_id", sa.Uuid(), nullable=True),
        sa.Column("agent_key", sa.String(length=64), nullable=False),
        sa.Column("agent_version", sa.String(length=64), nullable=False),
        sa.Column("agent_name", sa.String(length=120), nullable=False),
        sa.Column("responsibility", sa.Text(), nullable=False),
        sa.Column("current_task", sa.Text(), nullable=False),
        sa.Column(
            "input_scope_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "allowed_tools",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("expected_output", sa.Text(), nullable=True),
        sa.Column("allow_write", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("current_tool", sa.String(length=120), nullable=True),
        sa.Column("progress_current", sa.Integer(), nullable=True),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("stage_label", sa.String(length=120), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('pending','running','waiting_confirmation','success',"
            "'partial_success','failed','skipped')",
            name=op.f("ck_agent_runs_agent_run_status"),
        ),
        sa.CheckConstraint(
            "progress_current is null or progress_current >= 0",
            name=op.f("ck_agent_runs_agent_run_progress_current_nonnegative"),
        ),
        sa.CheckConstraint(
            "progress_total is null or progress_total >= 0",
            name=op.f("ck_agent_runs_agent_run_progress_total_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_run_id"],
            ["agent_runs.id"],
            name=op.f("fk_agent_runs_parent_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["agent_tasks.id"],
            name=op.f("fk_agent_runs_task_id_agent_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
    )
    op.create_index("ix_agent_runs_parent_run_id", "agent_runs", ["parent_run_id"])
    op.create_index(
        "ix_agent_runs_task_started_at", "agent_runs", ["task_id", "started_at"]
    )

    op.create_table(
        "agent_execution_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("agent_name", sa.String(length=120), nullable=False),
        sa.Column("step_label", sa.String(length=200), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("operation_type", sa.String(length=16), nullable=False),
        sa.Column(
            "params_digest_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "operation_type in ('query','analyze','create','update','delete',"
            "'publish','rollback')",
            name=op.f("ck_agent_execution_records_agent_execution_operation_type"),
        ),
        sa.CheckConstraint(
            "status in ('success','failed','skipped')",
            name=op.f("ck_agent_execution_records_agent_execution_status"),
        ),
        sa.CheckConstraint(
            "duration_ms is null or duration_ms >= 0",
            name=op.f("ck_agent_execution_records_agent_execution_duration_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name=op.f("fk_agent_execution_records_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["agent_tasks.id"],
            name=op.f("fk_agent_execution_records_task_id_agent_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_execution_records")),
    )
    op.create_index(
        "ix_agent_execution_records_task_id_id",
        "agent_execution_records",
        ["task_id", "id"],
    )

    op.create_table(
        "agent_pending_writes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("operation_type", sa.String(length=16), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=False),
        sa.Column("targets_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("preview_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("affected_count", sa.Integer(), nullable=False),
        sa.Column("reversible", sa.Boolean(), nullable=False),
        sa.Column("high_risk", sa.Boolean(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation_type in ('query','analyze','create','update','delete',"
            "'publish','rollback')",
            name=op.f("ck_agent_pending_writes_agent_pending_write_operation_type"),
        ),
        sa.CheckConstraint(
            "decision in ('pending','approved','rejected','expired')",
            name=op.f("ck_agent_pending_writes_agent_pending_write_decision"),
        ),
        sa.CheckConstraint(
            "affected_count >= 0",
            name=op.f("ck_agent_pending_writes_agent_pending_write_affected_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name=op.f("fk_agent_pending_writes_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["agent_tasks.id"],
            name=op.f("fk_agent_pending_writes_task_id_agent_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_pending_writes")),
    )
    op.create_index(
        "ix_agent_pending_writes_task_decision",
        "agent_pending_writes",
        ["task_id", "decision"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_pending_writes_task_decision", table_name="agent_pending_writes"
    )
    op.drop_table("agent_pending_writes")
    op.drop_index(
        "ix_agent_execution_records_task_id_id", table_name="agent_execution_records"
    )
    op.drop_table("agent_execution_records")
    op.drop_index("ix_agent_runs_task_started_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_parent_run_id", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_agent_tasks_user_created_at", table_name="agent_tasks")
    op.drop_table("agent_tasks")
