"""Migration guarantees for spec 005 (T007).

The session-scoped fixture runs Alembic to head, so these tests assert the
resulting schema: additive blog tables exist, new Post columns backfill to safe
defaults, existing publication semantics are untouched, and the migration
declares a reversible downgrade.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from app.db.session import get_session_factory, session_scope
from app.models.posts import Post
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

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
        post = Post(
            id=uuid.uuid4(), user_id=user.id, title="默认值", markdown="正文", status="draft"
        )
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
        row = s.execute(text("SELECT status FROM posts WHERE slug = :slug"), {"slug": slug}).one()
        assert row.status == "published"


def test_migration_declares_reversible_downgrade():
    path = Path(__file__).resolve().parents[2] / "alembic/versions/0011_blog_content_management.py"
    spec = importlib.util.spec_from_file_location("_mig_0011", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "downgrade") and callable(mod.downgrade)
    assert mod.down_revision == "0010_task_note_any_attachment"


def test_existing_post_upgrades_and_legacy_projection_remains_readable():
    """Exercise 0010 -> head with real legacy data in an isolated database.

    Application rollback means deploying the pre-feature binary against the
    additive head schema, not destructively downgrading article data. The final
    legacy SELECT proves that old Post/public projections remain available.
    """
    import psycopg
    from psycopg import sql

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    database_name = f"aiassist_migration_{uuid.uuid4().hex[:12]}"
    admin_dsn = base_url.set(database="postgres").render_as_string(hide_password=False)
    target_url = base_url.set(database=database_name).render_as_string(hide_password=False)
    admin_dsn = admin_dsn.replace("postgresql+psycopg://", "postgresql://")
    target_dsn = target_url.replace("postgresql+psycopg://", "postgresql://")
    backend_dir = Path(__file__).resolve().parents[2]
    env = {**os.environ, "DATABASE_URL": target_url, "TEST_DATABASE_URL": target_url}
    user_id, post_id, revision_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0010_task_note_any_attachment"],
            cwd=backend_dir,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        with psycopg.connect(target_dsn) as conn:
            conn.execute(
                """INSERT INTO users
                (id,email,password_hash,display_name,timezone,locale,status,notification_preferences)
                VALUES (%s,%s,'legacy-hash','Legacy','Europe/Berlin','zh-CN','active','{}')""",
                (user_id, f"legacy-{user_id}@example.com"),
            )
            conn.execute(
                """INSERT INTO posts
                (id,user_id,slug,title,markdown,status,version)
                VALUES (%s,%s,'legacy-public','旧文章','# 原始正文','published',7)""",
                (post_id, user_id),
            )
            conn.execute(
                """INSERT INTO post_revisions
                (id,user_id,post_id,source,markdown) VALUES (%s,%s,%s,'user','# 原始正文')""",
                (revision_id, user_id, post_id),
            )
            conn.execute(
                "UPDATE posts SET current_revision_id=%s WHERE id=%s", (revision_id, post_id)
            )
            conn.commit()

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend_dir,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        with psycopg.connect(target_dsn) as conn:
            upgraded = conn.execute(
                """SELECT title,markdown,status,version,content_status,content_class,
                          language,structured_data_json
                   FROM posts WHERE id=%s""",
                (post_id,),
            ).fetchone()
            assert upgraded == (
                "旧文章",
                "# 原始正文",
                "published",
                7,
                "draft",
                "essay",
                "zh-CN",
                {},
            )
            legacy_projection = conn.execute(
                "SELECT id,user_id,slug,title,markdown,status,version FROM posts WHERE id=%s",
                (post_id,),
            ).fetchone()
            assert legacy_projection == (
                post_id,
                user_id,
                "legacy-public",
                "旧文章",
                "# 原始正文",
                "published",
                7,
            )
            assert conn.execute(
                "SELECT markdown, source FROM post_revisions WHERE id=%s", (revision_id,)
            ).fetchone() == ("# 原始正文", "user")
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
                (database_name,),
            )
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
