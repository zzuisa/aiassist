"""Add the measured association index for the 100k word-cloud workload.

Revision ID: 0018_blog_wordcloud_index
Revises: 0017_taxonomy_alias_governance
"""

from alembic import op

revision = "0018_blog_wordcloud_index"
down_revision = "0017_taxonomy_alias_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_post_keyword_links_user_keyword_post",
        "post_keyword_links",
        ["user_id", "keyword_id", "post_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_post_keyword_links_user_keyword_post", table_name="post_keyword_links"
    )
