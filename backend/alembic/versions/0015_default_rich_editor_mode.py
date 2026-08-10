"""make rich text the default post editor mode

Revision ID: 0015_default_rich_editor_mode
Revises: 0014_ai_optimization_provider
Create Date: 2026-07-31 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_default_rich_editor_mode"
down_revision: str | None = "0014_ai_optimization_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing rows still carry the former default. Convert them once so an
    # article opens in rich text immediately after this release.
    op.execute(sa.text("UPDATE posts SET editor_mode = 'rich' WHERE editor_mode = 'markdown'"))
    op.alter_column(
        "posts",
        "editor_mode",
        existing_type=sa.String(length=10),
        server_default="rich",
        existing_nullable=False,
    )


def downgrade() -> None:
    # Do not rewrite article preferences on downgrade; only restore the
    # database default for subsequently created rows.
    op.alter_column(
        "posts",
        "editor_mode",
        existing_type=sa.String(length=10),
        server_default="markdown",
        existing_nullable=False,
    )
