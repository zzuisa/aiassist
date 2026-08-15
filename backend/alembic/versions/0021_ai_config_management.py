"""Add user-owned, versioned AI prompt and skill configuration."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_ai_config_management"
down_revision: str | None = "0020_conversational_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_config_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_key", sa.String(length=80), nullable=False),
        sa.Column("active_prompt_version_id", sa.Uuid(), nullable=True),
        sa.Column("active_skill_version_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "module_key", name="uq_ai_config_profile_user_module"),
    )
    op.create_table(
        "ai_prompt_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["ai_config_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id", "version_number", name="uq_ai_prompt_version_profile_number"
        ),
    )
    op.create_index("ix_ai_prompt_versions_profile", "ai_prompt_versions", ["profile_id"])
    op.create_table(
        "ai_skill_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("allowed_tool_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("parameter_defaults", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_guidance", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["ai_config_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id", "version_number", name="uq_ai_skill_version_profile_number"
        ),
    )
    op.create_index("ix_ai_skill_versions_profile", "ai_skill_versions", ["profile_id"])
    op.create_foreign_key(
        "fk_ai_config_profiles_active_prompt",
        "ai_config_profiles",
        "ai_prompt_versions",
        ["active_prompt_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_config_profiles_active_skill",
        "ai_config_profiles",
        "ai_skill_versions",
        ["active_skill_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_ai_config_profiles_active_skill", "ai_config_profiles", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_ai_config_profiles_active_prompt", "ai_config_profiles", type_="foreignkey"
    )
    op.drop_index("ix_ai_skill_versions_profile", table_name="ai_skill_versions")
    op.drop_table("ai_skill_versions")
    op.drop_index("ix_ai_prompt_versions_profile", table_name="ai_prompt_versions")
    op.drop_table("ai_prompt_versions")
    op.drop_table("ai_config_profiles")
