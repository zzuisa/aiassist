"""Enforce owner-scoped case-insensitive taxonomy alias uniqueness.

Revision ID: 0017_taxonomy_alias_governance
Revises: 0016_blog_search_indexes
"""

from alembic import op

revision: str = "0017_taxonomy_alias_governance"
down_revision: str | None = "0016_blog_search_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_tag_alias_user_alias", "post_tag_aliases", type_="unique"
    )
    op.drop_constraint(
        "uq_keyword_alias_user_alias", "post_keyword_aliases", type_="unique"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_tag_alias_user_alias_ci "
        "ON post_tag_aliases (user_id, lower(alias))"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_keyword_alias_user_alias_ci "
        "ON post_keyword_aliases (user_id, lower(alias))"
    )


def downgrade() -> None:
    op.drop_index("uq_keyword_alias_user_alias_ci", table_name="post_keyword_aliases")
    op.drop_index("uq_tag_alias_user_alias_ci", table_name="post_tag_aliases")
    op.create_unique_constraint(
        "uq_keyword_alias_user_alias",
        "post_keyword_aliases",
        ["user_id", "alias"],
    )
    op.create_unique_constraint(
        "uq_tag_alias_user_alias", "post_tag_aliases", ["user_id", "alias"]
    )
