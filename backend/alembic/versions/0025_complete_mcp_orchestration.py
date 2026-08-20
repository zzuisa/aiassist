"""Persist capability snapshots, report projections, and public plan phases."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025_complete_mcp_orchestration"
down_revision = "0024_langgraph_runtime_refs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_capability_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("manifest_version", sa.String(40), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("capability_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "capability_count >= 0 and capability_count <= 100",
            name=op.f("ck_agent_capability_snapshots_agent_capability_snapshot_count"),
        ),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_agent_capability_snapshots_task_id"),
    )
    op.create_index(
        "ix_agent_capability_snapshots_user_created",
        "agent_capability_snapshots",
        ["user_id", "created_at"],
    )
    op.create_table(
        "agent_capability_snapshot_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("safe_name", sa.String(64), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("definition_version", sa.String(64), nullable=False),
        sa.Column("catalog_version", sa.String(64)),
        sa.Column("tool_type", sa.String(16), nullable=False),
        sa.Column("responsibility", sa.String(500), nullable=False),
        sa.Column("input_schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_schema_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("risk_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("required_permission", sa.String(120)),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("unavailable_reason", sa.String(500)),
        sa.Column("connection_id", sa.Uuid()),
        sa.Column("provider_tool_key", sa.String(160), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("idempotency_mode", sa.String(16), nullable=False),
        sa.Column("verification_mode", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source in ('internal_api','mcp')",
            name=op.f("ck_agent_capability_snapshot_items_agent_capability_source"),
        ),
        sa.CheckConstraint(
            "tool_type in ('read','write')",
            name=op.f("ck_agent_capability_snapshot_items_agent_capability_tool_type"),
        ),
        sa.CheckConstraint(
            "max_retries >= 0 and max_retries <= 2",
            name=op.f("ck_agent_capability_snapshot_items_agent_capability_retries"),
        ),
        sa.ForeignKeyConstraint(["connection_id"], ["mcp_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["agent_capability_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_id", "safe_name", name="uq_agent_capability_snapshot_items_safe_name"
        ),
    )
    op.create_index(
        "ix_agent_capability_snapshot_items_snapshot",
        "agent_capability_snapshot_items",
        ["snapshot_id"],
    )
    op.add_column("agent_execution_plans", sa.Column("capability_snapshot_id", sa.Uuid()))
    op.add_column(
        "agent_execution_plans",
        sa.Column("phase", sa.String(32), nullable=False, server_default="planning"),
    )
    for name in ("verified_count", "conflict_count", "unprocessed_count", "waiting_count"):
        op.add_column(
            "agent_execution_plans",
            sa.Column(name, sa.Integer(), nullable=False, server_default="0"),
        )
    op.create_foreign_key(
        "fk_agent_plans_capability_snapshot",
        "agent_execution_plans",
        "agent_capability_snapshots",
        ["capability_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "agent_execution_plan_phase",
        "agent_execution_plans",
        "phase in ('planning','executing','waiting_confirmation','verifying','reporting','complete')",
    )
    op.create_table(
        "agent_task_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("totals_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("facts_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("short_summary", sa.String(1000), nullable=False),
        sa.Column("generation_method", sa.String(24), nullable=False),
        sa.Column("validation_status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "revision >= 1", name=op.f("ck_agent_task_reports_agent_task_report_revision")
        ),
        sa.CheckConstraint(
            "status in ('generating','ready','failed')",
            name=op.f("ck_agent_task_reports_agent_task_report_status"),
        ),
        sa.CheckConstraint(
            "generation_method in ('deterministic','llm_enhanced')",
            name=op.f("ck_agent_task_reports_agent_task_report_generation_method"),
        ),
        sa.CheckConstraint(
            "validation_status in ('valid','invalid')",
            name=op.f("ck_agent_task_reports_agent_task_report_validation"),
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["agent_execution_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "revision", name="uq_agent_task_reports_plan_revision"),
    )
    op.create_index(
        "ix_agent_task_reports_plan_created", "agent_task_reports", ["plan_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_task_reports_plan_created", table_name="agent_task_reports")
    op.drop_table("agent_task_reports")
    op.drop_constraint("agent_execution_plan_phase", "agent_execution_plans", type_="check")
    op.drop_constraint(
        "fk_agent_plans_capability_snapshot",
        "agent_execution_plans",
        type_="foreignkey",
    )
    for name in (
        "waiting_count",
        "unprocessed_count",
        "conflict_count",
        "verified_count",
        "phase",
        "capability_snapshot_id",
    ):
        op.drop_column("agent_execution_plans", name)
    op.drop_index(
        "ix_agent_capability_snapshot_items_snapshot", table_name="agent_capability_snapshot_items"
    )
    op.drop_table("agent_capability_snapshot_items")
    op.drop_index(
        "ix_agent_capability_snapshots_user_created", table_name="agent_capability_snapshots"
    )
    op.drop_table("agent_capability_snapshots")
