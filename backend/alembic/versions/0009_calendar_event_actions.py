"""calendar event actions: important reminders, task notes, note image assets

Revision ID: 0009_calendar_event_actions
Revises: 0008_posts
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_calendar_event_actions"
down_revision: str | None = "0008_posts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Reminder: purpose + anchor semantics for the dedicated 4h reminder ---
    op.add_column(
        "reminders",
        sa.Column("purpose", sa.String(length=24), nullable=False, server_default="custom"),
    )
    op.add_column(
        "reminders",
        sa.Column("anchor", sa.String(length=16), nullable=False, server_default="absolute"),
    )
    # Backfilled existing rows; drop the server default so it matches the model.
    op.alter_column("reminders", "purpose", server_default=None)
    op.alter_column("reminders", "anchor", server_default=None)
    op.create_check_constraint(
        "reminder_purpose", "reminders", "purpose in ('custom','important_start_4h')"
    )
    op.create_check_constraint(
        "reminder_anchor", "reminders", "anchor in ('absolute','due_at','start_at')"
    )
    op.create_index(
        "uq_reminders_important_start_4h",
        "reminders",
        ["user_id", "task_id", "channel"],
        unique=True,
        postgresql_where=sa.text("purpose = 'important_start_4h'"),
    )

    # --- task_notes: one mutable note per task ---
    op.create_table(
        "task_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "task_id", name="uq_task_notes_user_task"),
    )
    op.create_index(
        "ix_task_notes_user_task_deleted", "task_notes", ["user_id", "task_id", "deleted_at"]
    )

    # --- task_note_assets: one logical image attached to a note ---
    op.create_table(
        "task_note_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("preview_storage_key", sa.String(length=512), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("processing_status", sa.String(length=16), nullable=False),
        sa.Column("processing_version", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("async_job_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["note_id"], ["task_notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_id"], ["upload_sessions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upload_id", name="uq_task_note_assets_upload"),
        sa.UniqueConstraint("note_id", "position", name="uq_task_note_assets_note_position"),
        sa.CheckConstraint(
            "processing_status in ('pending','processing','ready','failed','deleted')",
            name="task_note_asset_status",
        ),
        sa.CheckConstraint(
            "media_type in ('image/jpeg','image/png','image/webp')",
            name="task_note_asset_media_type",
        ),
    )
    op.create_index(
        "ix_task_note_assets_user_note_deleted",
        "task_note_assets",
        ["user_id", "note_id", "deleted_at"],
    )

    # --- upload_sessions: allow the task_note_image purpose ---
    op.drop_constraint("upload_purpose", "upload_sessions", type_="check")
    op.create_check_constraint(
        "upload_purpose",
        "upload_sessions",
        "purpose in ('capture','voice','post_cover','attachment','task_note_image')",
    )


def downgrade() -> None:
    op.drop_constraint("upload_purpose", "upload_sessions", type_="check")
    op.create_check_constraint(
        "upload_purpose",
        "upload_sessions",
        "purpose in ('capture','voice','post_cover','attachment')",
    )
    op.drop_index("ix_task_note_assets_user_note_deleted", table_name="task_note_assets")
    op.drop_table("task_note_assets")
    op.drop_index("ix_task_notes_user_task_deleted", table_name="task_notes")
    op.drop_table("task_notes")
    op.drop_index("uq_reminders_important_start_4h", table_name="reminders")
    op.drop_constraint("reminder_anchor", "reminders", type_="check")
    op.drop_constraint("reminder_purpose", "reminders", type_="check")
    op.drop_column("reminders", "anchor")
    op.drop_column("reminders", "purpose")
