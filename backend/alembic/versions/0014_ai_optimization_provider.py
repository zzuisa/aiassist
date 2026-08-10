"""bind AI optimization runs to an explicit provider

Revision ID: 0014_ai_optimization_provider
Revises: 0013_radio_bilibili_import
Create Date: 2026-07-30 23:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_ai_optimization_provider"
down_revision: str | None = "0013_radio_bilibili_import"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Historical runs all used AI Assist's gateway. New code explicitly writes
    # the chosen provider, whose user-level default is Radio.
    op.add_column(
        "post_ai_runs",
        sa.Column(
            "provider_key",
            sa.String(32),
            nullable=False,
            server_default="aiassist",
        ),
    )
    op.create_check_constraint(
        "ai_run_provider",
        "post_ai_runs",
        "provider_key in ('radio','aiassist')",
    )
    op.alter_column("post_ai_runs", "provider_key", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ai_run_provider", "post_ai_runs", type_="check")
    op.drop_column("post_ai_runs", "provider_key")
