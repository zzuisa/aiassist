"""Tune owner-scoped Post deep search and timeline indexes.

Revision ID: 0016_blog_search_indexes
Revises: 0015_default_rich_editor_mode
"""

from alembic import op

revision: str = "0016_blog_search_indexes"
down_revision: str | None = "0015_default_rich_editor_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # EXPLAIN on the 100k acceptance corpus showed owner filtering and timeline
    # ordering as stable selective prefixes; trigram GIN covers CJK/code ILIKE.
    op.execute(
        "CREATE INDEX ix_posts_user_timeline ON posts "
        "(user_id, (COALESCE(occurred_at, created_at)) DESC, id DESC)"
    )
    op.execute("CREATE INDEX ix_posts_title_trgm ON posts USING gin (title gin_trgm_ops)")
    op.execute("CREATE INDEX ix_posts_markdown_trgm ON posts USING gin (markdown gin_trgm_ops)")
    op.execute("CREATE INDEX ix_posts_summary_trgm ON posts USING gin (summary gin_trgm_ops)")
    op.execute(
        "CREATE INDEX ix_posts_structured_data_trgm ON posts USING gin "
        "((structured_data_json::text) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_posts_structured_data_trgm", table_name="posts", postgresql_using="gin")
    op.drop_index("ix_posts_summary_trgm", table_name="posts", postgresql_using="gin")
    op.drop_index("ix_posts_markdown_trgm", table_name="posts", postgresql_using="gin")
    op.drop_index("ix_posts_title_trgm", table_name="posts", postgresql_using="gin")
    op.drop_index("ix_posts_user_timeline", table_name="posts")
