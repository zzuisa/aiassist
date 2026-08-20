"""Add LangGraph runtime references to the plan projection."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0024_langgraph_runtime_refs"
down_revision = "0023_collaborative_agent_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_agent_tasks_agent_task_status"), "agent_tasks", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_tasks_agent_task_status"),
        "agent_tasks",
        "status in ('pending','running','waiting_confirmation','success',"
        "'partial_success','failed','cancelled')",
    )
    op.add_column("agent_execution_plans", sa.Column("graph_thread_id", sa.String(128)))
    op.add_column("agent_execution_plans", sa.Column("graph_run_id", sa.String(128)))
    op.add_column(
        "agent_execution_plans",
        sa.Column("runtime_state", sa.String(24), nullable=False, server_default="checkpointed"),
    )
    op.create_unique_constraint(
        "uq_agent_execution_plans_graph_thread_id",
        "agent_execution_plans",
        ["graph_thread_id"],
    )
    op.create_check_constraint(
        "agent_execution_plan_runtime_state",
        "agent_execution_plans",
        "runtime_state in ('checkpointed','running','interrupted','completed','failed')",
    )


def downgrade() -> None:
    op.drop_constraint("agent_execution_plan_runtime_state", "agent_execution_plans", type_="check")
    op.drop_constraint(
        "uq_agent_execution_plans_graph_thread_id", "agent_execution_plans", type_="unique"
    )
    op.drop_column("agent_execution_plans", "runtime_state")
    op.drop_column("agent_execution_plans", "graph_run_id")
    op.drop_column("agent_execution_plans", "graph_thread_id")
    op.drop_constraint(op.f("ck_agent_tasks_agent_task_status"), "agent_tasks", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_tasks_agent_task_status"),
        "agent_tasks",
        "status in ('pending','running','waiting_confirmation','success',"
        "'partial_success','failed')",
    )
