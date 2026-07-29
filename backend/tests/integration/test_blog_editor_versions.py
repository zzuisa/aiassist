"""Complete-snapshot revisioning, restore and optimistic conflict (T010).

Every user save writes a full ``snapshot_json``; restoring a past revision
projects that snapshot back onto the current Post as a NEW ``restore`` revision
without mutating history, and stale-version restores/saves are rejected.
"""

from __future__ import annotations

import pytest

from app.core.errors import VersionConflictError
from app.db.session import session_scope
from app.models.posts import Post, PostRevision
from app.modules.posts import service as post_service

pytestmark = [pytest.mark.integration]


def test_user_save_writes_full_snapshot(make_user):
    user = make_user()
    with session_scope() as s:
        post = post_service.create_post(s, user.id, title="标题一", markdown="正文一")
        pid = post.id

    with session_scope() as s:
        post = s.get(Post, pid)
        post_service.save_user_revision(
            s, user.id, pid, title="标题二", markdown="正文二", version=post.version
        )

    with session_scope() as s:
        rev = (
            s.query(PostRevision)
            .filter(PostRevision.post_id == pid)
            .order_by(PostRevision.created_at.desc())
            .first()
        )
        snap = rev.snapshot_json
        assert snap["schema_version"] == "post-revision.v1"
        assert snap["title"] == "标题二"
        assert snap["markdown"] == "正文二"


def test_restore_creates_new_revision_without_mutating_history(make_user):
    user = make_user()
    with session_scope() as s:
        post = post_service.create_post(s, user.id, title="原标题", markdown="原正文")
        pid = post.id
        first_rev_id = post.current_revision_id

    # Edit away from the original.
    with session_scope() as s:
        post = s.get(Post, pid)
        post_service.save_user_revision(
            s, user.id, pid, title="改后标题", markdown="改后正文", version=post.version
        )

    # Restore the first revision.
    with session_scope() as s:
        post = s.get(Post, pid)
        post_service.restore_revision(
            s, user.id, pid, first_rev_id, current_version=post.version
        )

    with session_scope() as s:
        post = s.get(Post, pid)
        assert post.markdown == "原正文"
        assert post.title == "原标题"
        # A brand-new revision was created; the original still exists untouched.
        revs = s.query(PostRevision).filter(PostRevision.post_id == pid).all()
        assert len(revs) >= 3
        newest = max(revs, key=lambda r: r.created_at)
        assert newest.source == "restore"
        assert newest.id != first_rev_id


def test_restore_with_stale_version_is_rejected(make_user):
    user = make_user()
    with session_scope() as s:
        post = post_service.create_post(s, user.id, title="标题", markdown="正文")
        pid = post.id
        rev_id = post.current_revision_id
        stale_version = post.version

    with session_scope() as s:
        post = s.get(Post, pid)
        post_service.save_user_revision(
            s, user.id, pid, title="标题+", markdown="正文+", version=post.version
        )

    with session_scope() as s:
        with pytest.raises(VersionConflictError):
            post_service.restore_revision(
                s, user.id, pid, rev_id, current_version=stale_version
            )


def test_save_with_stale_version_is_rejected(make_user):
    user = make_user()
    with session_scope() as s:
        post = post_service.create_post(s, user.id, title="标题", markdown="正文")
        pid = post.id
        stale_version = post.version

    with session_scope() as s:
        post = s.get(Post, pid)
        post_service.save_user_revision(
            s, user.id, pid, title="v2", markdown="v2", version=post.version
        )

    with session_scope() as s:
        with pytest.raises(VersionConflictError):
            post_service.save_user_revision(
                s, user.id, pid, title="v3", markdown="v3", version=stale_version
            )
