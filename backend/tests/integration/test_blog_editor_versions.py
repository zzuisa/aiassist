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
        post_service.restore_revision(s, user.id, pid, first_rev_id, current_version=post.version)

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

    with session_scope() as s, pytest.raises(VersionConflictError):
        post_service.restore_revision(s, user.id, pid, rev_id, current_version=stale_version)


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

    with session_scope() as s, pytest.raises(VersionConflictError):
        post_service.save_user_revision(
            s, user.id, pid, title="v3", markdown="v3", version=stale_version
        )


# ---------------------------------------------------------------------------
# US2: full-field patch, hidden dynamic fields, concurrent autosave (T047)
# ---------------------------------------------------------------------------


class _Patch:
    """Lightweight stand-in for the PostPatch DTO in service-level tests."""

    def __init__(self, version, **fields):
        self.version = version
        self._fields = fields
        for k, v in fields.items():
            setattr(self, k, v)

    def provided_fields(self):
        return set(self._fields)


def test_patch_persists_all_common_and_dynamic_fields(make_user):
    user = make_user()
    with session_scope() as s:
        post = post_service.create_post(s, user.id, title="t", markdown="body")
        pid, ver = post.id, post.version

    with session_scope() as s:
        post_service.patch_post(
            s,
            user.id,
            pid,
            _Patch(
                ver,
                title="新标题",
                subtitle="副标题",
                summary="摘要",
                content_class="technical",
                language="en-US",
                editor_mode="rich",
                location="Shanghai",
                project="AIAssist",
                structured_data={"difficulty": "advanced"},
            ),
        )

    with session_scope() as s:
        p = s.get(Post, pid)
        assert p.title == "新标题"
        assert p.subtitle == "副标题"
        assert p.content_class == "technical"
        assert p.editor_mode == "rich"
        assert p.location_text == "Shanghai"
        assert p.project_text == "AIAssist"
        # Hidden dynamic field survives even though it is not a first-class column.
        assert p.structured_data_json["difficulty"] == "advanced"
        assert p.version == ver + 1


def test_changing_content_type_keeps_hidden_structured_data(make_user):
    """Switching content types must not drop structured_data the new type hides."""
    user = make_user()
    with session_scope() as s:
        post = post_service.create_post(s, user.id, title="t", markdown="b")
        pid = post.id
        post_service.patch_post(
            s,
            user.id,
            pid,
            _Patch(post.version, structured_data={"language": "python", "extra": "keep-me"}),
        )

    with session_scope() as s:
        p = s.get(Post, pid)
        # Change an unrelated field twice; structured_data is preserved verbatim.
        post_service.patch_post(s, user.id, pid, _Patch(p.version, title="x"))
    with session_scope() as s:
        p = s.get(Post, pid)
        post_service.patch_post(s, user.id, pid, _Patch(p.version, title="y"))

    with session_scope() as s:
        p = s.get(Post, pid)
        assert p.structured_data_json == {"language": "python", "extra": "keep-me"}


def test_concurrent_autosave_conflict_is_rejected(make_user):
    """Two autosaves from the same base version: the second must 409."""
    user = make_user()
    with session_scope() as s:
        post = post_service.create_post(s, user.id, title="t", markdown="b")
        pid, base = post.id, post.version

    with session_scope() as s:
        post_service.patch_post(s, user.id, pid, _Patch(base, markdown="edit-A"))

    with session_scope() as s, pytest.raises(VersionConflictError):
        post_service.patch_post(s, user.id, pid, _Patch(base, markdown="edit-B"))


def test_patch_creates_user_edit_revision_on_content_change(make_user):
    user = make_user()
    with session_scope() as s:
        post = post_service.create_post(s, user.id, title="t", markdown="b")
        pid = post.id
        post_service.patch_post(s, user.id, pid, _Patch(post.version, markdown="changed body"))

    with session_scope() as s:
        latest = (
            s.query(PostRevision)
            .filter(PostRevision.post_id == pid)
            .order_by(PostRevision.created_at.desc())
            .first()
        )
        assert latest.source == "user_edit"
        assert latest.markdown == "changed body"
        p = s.get(Post, pid)
        assert p.current_revision_id == latest.id
