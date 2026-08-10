"""task note attachments: allow non-image files (drop image-only media_type check)

Revision ID: 0010_task_note_any_attachment
Revises: 0009_calendar_event_actions
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_task_note_any_attachment"
down_revision: str | None = "0009_calendar_event_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Attachments are no longer image-only; the allowed set is enforced in the
    # service layer (a whitelist), so the DB no longer pins media_type to images.
    op.drop_constraint("task_note_asset_media_type", "task_note_assets", type_="check")


def downgrade() -> None:
    op.create_check_constraint(
        "task_note_asset_media_type",
        "task_note_assets",
        "media_type in ('image/jpeg','image/png','image/webp')",
    )
