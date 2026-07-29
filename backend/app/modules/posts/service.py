"""Post service: drafts, immutable revisions, diff/apply, publish/unpublish.

AI revisions are created without changing ``current_revision_id``; only an
explicit apply (with a base-revision conflict check) advances the current text.
Publishing requires an explicit call and assigns a unique slug.

Extended in spec 005 (T019):
- ``_build_snapshot`` captures the full restorable post state.
- ``_apply_snapshot`` projects selected fields from a snapshot back onto a Post.
- ``restore_revision`` restores a past revision as a new ``restore`` revision.
- ``validate_selected_fields`` guards the allow-list of applyable fields.
"""

from __future__ import annotations

import difflib
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError, VersionConflictError
from app.models.foundation import ActivityLog
from app.models.posts import Post, PostRevision
from app.models.relations import EntityRelation
from app.services.outbox.publisher import append_event


# ---------------------------------------------------------------------------
# Allow-list of top-level fields that a candidate application may write.
# Structured-data subkeys are also allowed as "structured_data.<defined-key>".
# ---------------------------------------------------------------------------
_APPLYABLE_TOP_FIELDS = frozenset(
    {
        "title",
        "subtitle",
        "summary",
        "markdown",
        "content_class",
        "content_type_id",
        "language",
        "structured_data",
    }
)


def validate_selected_fields(fields: list[str]) -> None:
    """Raise ValidationError if any path in *fields* is not on the allow-list.

    Valid paths are either a plain top-level name (e.g. ``"title"``) or a
    structured-data sub-key in dotted notation (e.g. ``"structured_data.tags"``).
    """
    for path in fields:
        parts = path.split(".", 1)
        top = parts[0]
        if top not in _APPLYABLE_TOP_FIELDS:
            raise ValidationError(
                f"Field '{path}' is not on the apply allow-list", code="invalid_field_path"
            )


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def _build_snapshot(post: Post) -> dict[str, Any]:
    """Capture the full restorable state of *post* as a plain dict.

    This dict is stored as ``PostRevision.snapshot_json`` so that any revision
    can be fully restored without relying on field-level diffs.
    """
    return {
        "schema_version": "post-revision.v1",
        "title": post.title,
        "markdown": post.markdown,
        "content_class": getattr(post, "content_class", "essay"),
        "content_type_id": (
            str(post.content_type_id) if getattr(post, "content_type_id", None) else None
        ),
        "language": getattr(post, "language", "zh-CN"),
        "structured_data": dict(getattr(post, "structured_data_json", None) or {}),
        "summary": getattr(post, "summary", None),
        "subtitle": getattr(post, "subtitle", None),
    }


def _apply_snapshot(
    post: Post,
    snapshot: dict[str, Any],
    selected_fields: list[str] | None = None,
) -> None:
    """Apply *snapshot* fields onto *post* in place.

    If *selected_fields* is given only those paths are applied; otherwise all
    top-level fields in the snapshot are applied (restore semantics).
    """
    fields_to_apply = selected_fields if selected_fields is not None else list(_APPLYABLE_TOP_FIELDS)

    for path in fields_to_apply:
        parts = path.split(".", 1)
        top = parts[0]
        if top not in snapshot:
            continue
        value = snapshot[top]
        if top == "content_type_id" and isinstance(value, str):
            try:
                value = uuid.UUID(value)
            except ValueError:
                value = None
        if top == "structured_data":
            if len(parts) == 2:
                # Update a single key inside structured_data.
                sub_key = parts[1]
                current = dict(getattr(post, "structured_data_json", None) or {})
                if isinstance(value, dict):
                    current[sub_key] = value.get(sub_key)
                post.structured_data_json = current  # type: ignore[assignment]
            else:
                post.structured_data_json = value  # type: ignore[assignment]
        else:
            # Map snapshot key → model attribute name.
            attr = "structured_data_json" if top == "structured_data" else top
            setattr(post, attr, value)


def _slugify(title: str) -> str:
    base = re.sub(r"[^\w一-鿿]+", "-", title.strip().lower()).strip("-")
    return base or "post"


def _new_revision(
    session: Session,
    post: Post,
    markdown: str,
    source: str,
    parent_id: uuid.UUID | None,
    change_summary: str | None = None,
    llm_log_id: uuid.UUID | None = None,
    *,
    snapshot: dict[str, Any] | None = None,
) -> PostRevision:
    """Create an immutable PostRevision row.

    ``snapshot`` is stored as ``snapshot_json`` for full restorability.  When
    *snapshot* is omitted a best-effort snapshot is built from the post's
    current in-memory state (covers the legacy caller paths).
    """
    resolved_snapshot = snapshot if snapshot is not None else _build_snapshot(post)
    revision = PostRevision(
        id=uuid.uuid4(),
        user_id=post.user_id,
        post_id=post.id,
        parent_revision_id=parent_id,
        source=source,
        markdown=markdown,
        change_summary=change_summary,
        llm_log_id=llm_log_id,
        snapshot_json=resolved_snapshot,
    )
    session.add(revision)
    session.flush()
    return revision


def create_post(
    session: Session,
    user_id: uuid.UUID,
    *,
    title: str,
    markdown: str,
    source_refs: list[dict] | None = None,
) -> Post:
    post = Post(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title,
        markdown=markdown,
        status="draft",
    )
    session.add(post)
    session.flush()
    revision = _new_revision(session, post, markdown, "user", None)
    revision.applied_at = datetime.now(UTC)
    post.current_revision_id = revision.id
    # Record source relations (e.g. from a completed task or capture).
    for ref in source_refs or []:
        session.add(
            EntityRelation(
                id=uuid.uuid4(),
                user_id=user_id,
                source_type=ref["type"],
                source_id=uuid.UUID(ref["id"]),
                target_type="post",
                target_id=post.id,
                relation_type="derived_from",
            )
        )
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="post.created",
            entity_type="post",
            entity_id=post.id,
        )
    )
    return post


def get_post(session: Session, user_id: uuid.UUID, post_id: uuid.UUID) -> Post:
    post = session.get(Post, post_id)
    if post is None or post.user_id != user_id or post.deleted_at is not None:
        raise NotFoundError("Post not found")
    return post


def list_posts(session: Session, user_id: uuid.UUID) -> list[Post]:
    return list(
        session.scalars(
            select(Post)
            .where(Post.user_id == user_id, Post.deleted_at.is_(None))
            .order_by(Post.updated_at.desc())
        ).all()
    )


def save_user_revision(
    session: Session,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    *,
    title: str,
    markdown: str,
    version: int,
) -> Post:
    post = get_post(session, user_id, post_id)
    if post.version != version:
        raise VersionConflictError("Post was modified; refresh", code="version_conflict")
    post.title = title
    post.markdown = markdown
    revision = _new_revision(session, post, markdown, "user", post.current_revision_id)
    revision.applied_at = datetime.now(UTC)
    post.current_revision_id = revision.id
    post.version += 1
    return post


def create_ai_revision(
    session: Session,
    post: Post,
    markdown: str,
    change_summary: str,
    llm_log_id: uuid.UUID | None = None,
) -> PostRevision:
    """Create an unapplied AI revision (does NOT change current text)."""
    return _new_revision(
        session,
        post,
        markdown,
        "ai",
        post.current_revision_id,
        change_summary=change_summary,
        llm_log_id=llm_log_id,
    )


def get_revision(
    session: Session, user_id: uuid.UUID, post_id: uuid.UUID, revision_id: uuid.UUID
) -> PostRevision:
    revision = session.get(PostRevision, revision_id)
    if revision is None or revision.user_id != user_id or revision.post_id != post_id:
        raise NotFoundError("Revision not found")
    return revision


def diff_revision(
    session: Session, user_id: uuid.UUID, post_id: uuid.UUID, revision_id: uuid.UUID
) -> dict:
    post = get_post(session, user_id, post_id)
    revision = get_revision(session, user_id, post_id, revision_id)
    current = post.markdown.splitlines(keepends=True)
    candidate = revision.markdown.splitlines(keepends=True)
    unified = "".join(
        difflib.unified_diff(current, candidate, fromfile="current", tofile="candidate")
    )
    return {
        "base_revision_id": str(post.current_revision_id),
        "candidate_revision_id": str(revision.id),
        "unified_diff": unified,
    }


def apply_revision(
    session: Session, user_id: uuid.UUID, post_id: uuid.UUID, revision_id: uuid.UUID
) -> Post:
    post = get_post(session, user_id, post_id)
    revision = get_revision(session, user_id, post_id, revision_id)
    # Base-revision conflict check: the candidate must branch from current text.
    if revision.parent_revision_id != post.current_revision_id:
        raise ConflictError(
            "The draft changed since this revision was generated; regenerate it.",
            code="base_conflict",
        )
    post.markdown = revision.markdown
    revision.applied_at = datetime.now(UTC)
    post.current_revision_id = revision.id
    post.version += 1
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="post.revision_applied",
            entity_type="post",
            entity_id=post.id,
        )
    )
    return post


def set_published(
    session: Session, user_id: uuid.UUID, post_id: uuid.UUID, published: bool, version: int
) -> Post:
    post = get_post(session, user_id, post_id)
    if post.version != version:
        raise VersionConflictError("Post was modified; refresh", code="version_conflict")
    now = datetime.now(UTC)
    if published:
        if not post.markdown.strip():
            raise ValidationError("Cannot publish an empty post", code="empty_post")
        if not post.slug:
            post.slug = f"{_slugify(post.title)}-{post.id.hex[:8]}"
        post.status = "published"
        post.published_at = now
        event = "post.published"
    else:
        post.status = "private"
        event = "post.unpublished"
    post.version += 1
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action=event,
            entity_type="post",
            entity_id=post.id,
        )
    )
    append_event(
        session,
        event_type=event,
        aggregate_type="post",
        aggregate_id=post.id,
        routing_key=f"search.index.post.{'published' if published else 'unpublished'}",
        payload={"post_id": str(post.id)},
        user_id=user_id,
    )
    return post


def delete_post(session: Session, user_id: uuid.UUID, post_id: uuid.UUID) -> None:
    post = get_post(session, user_id, post_id)
    if post.status == "published":
        raise ConflictError("Unpublish before deleting", code="published_post")
    post.deleted_at = datetime.now(UTC)
    post.version += 1


def get_public_post(session: Session, slug: str) -> Post | None:
    """Public read: only published, non-deleted posts by slug."""
    return session.scalar(
        select(Post).where(Post.slug == slug, Post.status == "published", Post.deleted_at.is_(None))
    )


def restore_revision(
    session: Session,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    revision_id: uuid.UUID,
    *,
    current_version: int,
) -> Post:
    """Restore a past revision as a new ``restore`` user revision.

    The historical chain is never mutated; instead a new revision is created
    from the target snapshot and the post's current projection is updated to
    match.  Uses the optimistic version lock (*current_version*) to reject
    concurrent edits.
    """
    post = get_post(session, user_id, post_id)
    if post.version != current_version:
        raise VersionConflictError("Post was modified; refresh", code="version_conflict")
    target = get_revision(session, user_id, post_id, revision_id)
    snapshot: dict[str, Any] = getattr(target, "snapshot_json", None) or {}
    if not snapshot:
        # Legacy revision with no snapshot — fall back to markdown-only restore.
        snapshot = _build_snapshot(post)
        snapshot["markdown"] = target.markdown

    # Apply the full snapshot onto the post projection.
    _apply_snapshot(post, snapshot)
    post.version += 1

    # Create a new immutable revision recording this restore.
    new_rev = _new_revision(
        session,
        post,
        post.markdown,
        "restore",
        post.current_revision_id,
        change_summary=f"Restored from revision {revision_id}",
        snapshot=snapshot,
    )
    new_rev.applied_at = datetime.now(UTC)
    post.current_revision_id = new_rev.id
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="post.revision_restored",
            entity_type="post",
            entity_id=post.id,
            details={"restored_from": str(revision_id)},
        )
    )
    return post


def list_published(session: Session, limit: int = 50) -> list[Post]:
    return list(
        session.scalars(
            select(Post)
            .where(Post.status == "published", Post.deleted_at.is_(None))
            .order_by(Post.published_at.desc())
            .limit(limit)
        ).all()
    )
