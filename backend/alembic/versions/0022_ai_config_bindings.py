"""Add immutable AI configuration call bindings."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_ai_config_bindings"
down_revision: str | None = "0021_ai_config_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_config_bindings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_key", sa.String(length=80), nullable=False),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=True),
        sa.Column("skill_version_id", sa.Uuid(), nullable=True),
        sa.Column("model_key", sa.String(length=120), nullable=False),
        sa.Column("run_reference", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"], ["ai_prompt_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["skill_version_id"], ["ai_skill_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_config_bindings_user_module_created",
        "ai_config_bindings",
        ["user_id", "module_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_config_bindings_user_module_created", table_name="ai_config_bindings")
    op.drop_table("ai_config_bindings")
