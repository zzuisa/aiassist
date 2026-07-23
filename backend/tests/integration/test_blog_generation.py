"""AI blog revision: non-overwrite, source grounding, diff/apply base-conflict."""

from __future__ import annotations

import pytest
from app.db.session import session_scope
from app.modules.posts import service as post_service

pytestmark = [pytest.mark.integration]


def _post(session, user_id, markdown="原始正文"):
    return post_service.create_post(session, user_id, title="文章", markdown=markdown)


def test_ai_revision_does_not_overwrite_current_text(make_user):
    user = make_user()
    with session_scope() as s:
        post = _post(s, user.id, "用户写的正文")
        original_rev = post.current_revision_id
        post_service.create_ai_revision(s, post, "AI 改写的正文", "优化")
        pid = post.id

    with session_scope() as s:
        from app.models.posts import Post

        post = s.get(Post, pid)
        # Current text and current revision are unchanged by AI generation.
        assert post.markdown == "用户写的正文"
        assert post.current_revision_id == original_rev


def test_apply_revision_advances_current_text(make_user):
    user = make_user()
    with session_scope() as s:
        post = _post(s, user.id, "旧正文")
        rev = post_service.create_ai_revision(s, post, "新正文", "改写")
        pid, rid = post.id, rev.id

    with session_scope() as s:
        post = post_service.apply_revision(s, user.id, pid, rid)
        assert post.markdown == "新正文"
        assert post.current_revision_id == rid


def test_apply_stale_revision_rejected_base_conflict(make_user):
    from app.core.errors import ConflictError

    user = make_user()
    with session_scope() as s:
        post = _post(s, user.id, "v1")
        rev = post_service.create_ai_revision(s, post, "AI 建议", "改写")
        pid, rid = post.id, rev.id

    # User edits the draft, moving current_revision forward.
    with session_scope() as s:
        from app.models.posts import Post

        post = s.get(Post, pid)
        post_service.save_user_revision(
            s, user.id, pid, title="文章", markdown="v2", version=post.version
        )

    # The old AI revision now branches from a stale base and cannot be applied.
    with session_scope() as s, pytest.raises(ConflictError):
        post_service.apply_revision(s, user.id, pid, rid)


def test_diff_shows_unified_changes(make_user):
    user = make_user()
    with session_scope() as s:
        post = _post(s, user.id, "line1\nline2\n")
        rev = post_service.create_ai_revision(s, post, "line1\nline2 changed\n", "改写")
        pid, rid = post.id, rev.id

    with session_scope() as s:
        diff = post_service.diff_revision(s, user.id, pid, rid)
        assert "line2 changed" in diff["unified_diff"]


def test_source_relation_recorded(make_user):
    import uuid

    user = make_user()
    source_id = uuid.uuid4()
    with session_scope() as s:
        post_service.create_post(
            s,
            user.id,
            title="来源文章",
            markdown="正文",
            source_refs=[{"type": "task", "id": str(source_id)}],
        )
        uid = user.id

    with session_scope() as s:
        from app.models.relations import EntityRelation
        from sqlalchemy import select

        rel = s.scalars(select(EntityRelation).where(EntityRelation.user_id == uid)).one()
        assert rel.target_type == "post"
        assert rel.relation_type == "derived_from"
