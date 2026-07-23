"""Post service: drafts, immutable revisions, diff/apply, publish/unpublish.

AI revisions are created without changing ``current_revision_id``; only an
explicit apply (with a base-revision conflict check) advances the current text.
Publishing requires an explicit call and assigns a unique slug.
"""

from __future__ import annotations

import difflib
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError, VersionConflictError
from app.models.foundation import ActivityLog
from app.models.posts import Post, PostRevision
from app.models.relations import EntityRelation
from app.services.outbox.publisher import append_event


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
) -> PostRevision:
    revision = PostRevision(
        id=uuid.uuid4(),
        user_id=post.user_id,
        post_id=post.id,
        parent_revision_id=parent_id,
        source=source,
        markdown=markdown,
        change_summary=change_summary,
        llm_log_id=llm_log_id,
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


def list_published(session: Session, limit: int = 50) -> list[Post]:
    return list(
        session.scalars(
            select(Post)
            .where(Post.status == "published", Post.deleted_at.is_(None))
            .order_by(Post.published_at.desc())
            .limit(limit)
        ).all()
    )
