"""add stable external identity for Radio/Bilibili imports

Revision ID: 0013_radio_bilibili_import
Revises: 0012_fix_revision_source
Create Date: 2026-07-30 22:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_radio_bilibili_import"
down_revision: str | None = "0012_fix_revision_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("post_sources", sa.Column("external_system", sa.String(32)))
    op.add_column("post_sources", sa.Column("external_record_id", sa.String(128)))
    op.add_column("post_sources", sa.Column("external_task_id", sa.String(128)))
    op.create_index(
        "uq_post_sources_external_record",
        "post_sources",
        ["user_id", "external_system", "external_record_id"],
        unique=True,
        postgresql_where=sa.text(
            "external_system is not null and external_record_id is not null"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_post_sources_external_record", table_name="post_sources")
    op.drop_column("post_sources", "external_task_id")
    op.drop_column("post_sources", "external_record_id")
    op.drop_column("post_sources", "external_system")
