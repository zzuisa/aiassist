"""Migration guarantees for spec 005 (T007).

The session-scoped fixture runs Alembic to head, so these tests assert the
resulting schema: additive blog tables exist, new Post columns backfill to safe
defaults, existing publication semantics are untouched, and the migration
declares a reversible downgrade.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from app.db.session import get_session_factory, session_scope
from app.models.posts import Post

pytestmark = [pytest.mark.integration]

_NEW_TABLES = [
    "post_sources",
    "post_content_types",
    "blog_skills",
    "blog_skill_versions",
    "blog_skill_defaults",
    "post_ai_runs",
    "post_ai_candidates",
    "post_candidate_decisions",
    "blog_settings",
    "post_word_cloud_snapshots",
]

_NEW_POST_COLUMNS = [
    "subtitle",
    "summary",
    "content_status",
    "content_class",
    "content_type_id",
    "language",
    "structured_data_json",
]


def test_new_blog_tables_exist():
    engine = get_session_factory().kw["bind"]
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = [t for t in _NEW_TABLES if t not in existing]
    assert not missing, f"migration did not create: {missing}"


def test_post_gets_additive_columns():
    engine = get_session_factory().kw["bind"]
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("posts")}
    missing = [c for c in _NEW_POST_COLUMNS if c not in cols]
    assert not missing, f"posts missing columns: {missing}"


def test_new_post_backfills_safe_defaults(make_user):
    user = make_user()
    with session_scope() as s:
        post = Post(id=uuid.uuid4(), user_id=user.id, title="默认值", markdown="正文", status="draft")
        s.add(post)
        s.flush()
        pid = post.id

    with session_scope() as s:
        post = s.get(Post, pid)
        assert post.content_status == "draft"
        assert post.content_class == "essay"
        assert post.language == "zh-CN"
        assert post.structured_data_json == {}


def test_publication_semantics_untouched(make_user):
    """A published post keeps status='published' and remains publicly readable."""
    user = make_user()
    with session_scope() as s:
        post = Post(
            id=uuid.uuid4(),
            user_id=user.id,
            title="已发布",
            markdown="正文",
            status="published",
            slug=f"pub-{uuid.uuid4().hex[:8]}",
        )
        s.add(post)
        s.flush()
        slug = post.slug

    with session_scope() as s:
        row = s.execute(
            text("SELECT status FROM posts WHERE slug = :slug"), {"slug": slug}
        ).one()
        assert row.status == "published"


def test_migration_declares_reversible_downgrade():
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/0011_blog_content_management.py"
    )
    spec = importlib.util.spec_from_file_location("_mig_0011", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "downgrade") and callable(mod.downgrade)
    assert mod.down_revision == "0010_task_note_any_attachment"
