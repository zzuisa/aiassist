"""fix post_revision_source check constraint

Widen ``post_revisions.source`` to the full revision-source vocabulary.

Migration 0011 was intended to widen this constraint, but the deployed 0011
only added the new columns — production is stamped at 0011 with the old
``source in ('user','ai')`` constraint still in place, so PATCH /posts and URL
capture (which write ``source='user_edit'`` / ``'capture'``) fail with a
CheckViolation. This migration re-applies the widening idempotently so any DB
stamped at 0011 converges regardless of which 0011 body it ran.

Revision ID: 0012_fix_revision_source
Revises: 0011_blog_content_management
Create Date: 2026-07-29 23:15:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = '0012_fix_revision_source'
down_revision: str | None = '0011_blog_content_management'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FULL_SOURCES = (
    "source in ('user','ai','capture','user_edit','ai_candidate',"
    "'ai_applied','restore','import','merge')"
)
_CONSTRAINT = 'ck_post_revisions_post_revision_source'


def upgrade() -> None:
    # Drop-if-exists then recreate: tolerant of both the narrow ('user','ai')
    # constraint and an already-widened one, so re-runs are safe.
    op.execute(f'ALTER TABLE post_revisions DROP CONSTRAINT IF EXISTS {_CONSTRAINT}')
    op.execute(
        f'ALTER TABLE post_revisions ADD CONSTRAINT {_CONSTRAINT} CHECK ({_FULL_SOURCES})'
    )


def downgrade() -> None:
    op.execute(f'ALTER TABLE post_revisions DROP CONSTRAINT IF EXISTS {_CONSTRAINT}')
    op.execute(
        "ALTER TABLE post_revisions ADD CONSTRAINT "
        f"{_CONSTRAINT} CHECK (source in ('user','ai'))"
    )
