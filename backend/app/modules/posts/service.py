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
    fields_to_apply = (
        selected_fields if selected_fields is not None else list(_APPLYABLE_TOP_FIELDS)
    )

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
                post.structured_data_json = current
            else:
                post.structured_data_json = value
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
        editor_mode="rich",
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


_CONTENT_STATUSES = frozenset(
    {
        "pending_capture",
        "pending_parse",
        "triage",
        "draft",
        "ai_queued",
        "ai_processing",
        "ai_review",
        "merge_required",
        "completed",
        "archived",
        "discarded",
    }
)
# Status transitions the *user* may drive directly from the editor. AI-only
# states (ai_queued/ai_processing/ai_review/merge_required) are set by the
# pipeline, never by a manual patch.
_USER_SETTABLE_STATUS = frozenset({"triage", "draft", "completed", "archived", "discarded"})


def patch_post(
    session: Session,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    patch: Any,
) -> tuple[Post, list[str]]:
    """Apply a partial update to a post (spec 005 US2, T051).

    Validates ownership of every referenced taxonomy entity, guards status
    transitions, validates structured_data against the content type, records a
    ``user_edit`` revision when content changed, and appends a search Outbox event.
    Returns ``(post, warnings)``; raises on version conflict or invalid reference.
    """
    from app.models.blog import PostContentType, PostKeyword, PostKeywordLink
    from app.models.foundation import Category, Tag
    from app.models.posts import PostTag
    from app.modules.posts import content_types

    post = get_post(session, user_id, post_id)
    if post.version != patch.version:
        raise VersionConflictError("Post was modified; refresh", code="version_conflict")

    provided = patch.provided_fields()
    warnings: list[str] = []
    content_changed = False

    if "content_class" in provided and patch.content_class is not None:
        content_types.validate_content_class(patch.content_class)
        post.content_class = patch.content_class

    if "content_type_id" in provided:
        if patch.content_type_id is not None:
            ct = session.get(PostContentType, patch.content_type_id)
            if ct is None or ct.user_id != user_id or not ct.enabled:
                raise ValidationError(
                    "content_type_id not found or disabled", code="invalid_content_type"
                )
        post.content_type_id = patch.content_type_id

    # Scalar common fields.
    if "title" in provided and patch.title is not None:
        post.title = patch.title
    if "subtitle" in provided:
        post.subtitle = patch.subtitle
    if "summary" in provided:
        post.summary = patch.summary
    if "language" in provided and patch.language is not None:
        post.language = patch.language
    if "editor_mode" in provided and patch.editor_mode is not None:
        post.editor_mode = patch.editor_mode
    if "occurred_at" in provided:
        post.occurred_at = patch.occurred_at
    if "location" in provided:
        post.location_text = patch.location
    if "project" in provided:
        post.project_text = patch.project

    if "markdown" in provided and patch.markdown is not None and patch.markdown != post.markdown:
        post.markdown = patch.markdown
        content_changed = True

    if "structured_data" in provided and patch.structured_data is not None:
        if post.content_type_id:
            warnings.extend(
                content_types.validate_structured_data(
                    session, user_id, post.content_type_id, patch.structured_data
                )
            )
        post.structured_data_json = patch.structured_data
        content_changed = True

    if "content_status" in provided and patch.content_status is not None:
        new_status = patch.content_status
        if new_status not in _CONTENT_STATUSES:
            raise ValidationError("invalid content_status", code="invalid_content_status")
        if new_status not in _USER_SETTABLE_STATUS:
            raise ValidationError(
                f"content_status '{new_status}' is not user-settable", code="invalid_transition"
            )
        post.content_status = new_status

    # Category (single, owned).
    if "category_id" in provided:
        if patch.category_id is not None:
            cat = session.get(Category, patch.category_id)
            if cat is None or cat.user_id != user_id:
                raise ValidationError("category_id not found", code="invalid_category")
        post.category_id = patch.category_id

    # Tags (replace set; each must be owned).
    if "tag_ids" in provided and patch.tag_ids is not None:
        _replace_links(session, user_id, post, patch.tag_ids, Tag, PostTag, "tag_id", "invalid_tag")

    # Keywords (replace set; each must be owned).
    if "keyword_ids" in provided and patch.keyword_ids is not None:
        _replace_keyword_links(
            session, user_id, post, patch.keyword_ids, PostKeyword, PostKeywordLink
        )

    # Record an immutable user_edit revision only when the canonical text changed.
    if content_changed:
        revision = _new_revision(
            session, post, post.markdown, "user_edit", post.current_revision_id
        )
        revision.applied_at = datetime.now(UTC)
        post.current_revision_id = revision.id

    post.version += 1
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="post.updated",
            entity_type="post",
            entity_id=post.id,
        )
    )
    # Keep the search index in sync.
    append_event(
        session,
        event_type="post.updated",
        aggregate_type="post",
        aggregate_id=post.id,
        routing_key="search.index.post.updated",
        payload={"post_id": str(post.id)},
        user_id=user_id,
    )
    return post, warnings


def _replace_links(
    session: Session,
    user_id: uuid.UUID,
    post: Post,
    ids: list[uuid.UUID],
    owner_model: Any,
    link_model: Any,
    link_attr: str,
    err_code: str,
) -> None:
    """Replace a post's M2M links (e.g. tags) with *ids*, validating ownership."""
    unique = list(dict.fromkeys(ids))
    for oid in unique:
        owner = session.get(owner_model, oid)
        if owner is None or owner.user_id != user_id:
            raise ValidationError(f"{link_attr} {oid} not found", code=err_code)
    for existing in session.scalars(select(link_model).where(link_model.post_id == post.id)).all():
        session.delete(existing)
    session.flush()
    for oid in unique:
        session.add(link_model(post_id=post.id, user_id=user_id, **{link_attr: oid}))


def _replace_keyword_links(
    session: Session,
    user_id: uuid.UUID,
    post: Post,
    ids: list[uuid.UUID],
    keyword_model: Any,
    link_model: Any,
) -> None:
    unique = list(dict.fromkeys(ids))
    for kid in unique:
        kw = session.get(keyword_model, kid)
        if kw is None or kw.user_id != user_id:
            raise ValidationError(f"keyword {kid} not found", code="invalid_keyword")
    for existing in session.scalars(select(link_model).where(link_model.post_id == post.id)).all():
        session.delete(existing)
    session.flush()
    for kid in unique:
        session.add(link_model(post_id=post.id, keyword_id=kid, user_id=user_id, source="user"))


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
            after_summary_json={"restored_from": str(revision_id)},
        )
    )
    return post


# ---------------------------------------------------------------------------
# Public snapshot/revision helpers reused by the AI candidate-merge flow (US4).
# ---------------------------------------------------------------------------


def build_snapshot(post: Post) -> dict[str, Any]:
    """Public wrapper: full restorable snapshot of *post*'s current state."""
    return _build_snapshot(post)


def apply_snapshot(
    post: Post, snapshot: dict[str, Any], selected_fields: list[str] | None = None
) -> None:
    """Public wrapper: apply *snapshot* (optionally only *selected_fields*)."""
    _apply_snapshot(post, snapshot, selected_fields)


def new_revision(
    session: Session,
    post: Post,
    markdown: str,
    source: str,
    parent_id: uuid.UUID | None,
    *,
    change_summary: str | None = None,
    snapshot: dict[str, Any] | None = None,
) -> PostRevision:
    """Public wrapper around ``_new_revision`` for cross-module callers."""
    return _new_revision(
        session,
        post,
        markdown,
        source,
        parent_id,
        change_summary=change_summary,
        snapshot=snapshot,
    )


def compare_revisions(
    session: Session,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    from_revision_id: uuid.UUID,
    to_revision_id: uuid.UUID,
) -> dict[str, Any]:
    """Two-version body + field comparison for the version timeline (US4)."""
    from app.modules.posts import diffing

    a = get_revision(session, user_id, post_id, from_revision_id)
    b = get_revision(session, user_id, post_id, to_revision_id)
    a_snap = dict(a.snapshot_json or {})
    b_snap = dict(b.snapshot_json or {})
    # Two-way: any field that differs between a and b surfaces as non-unchanged.
    fields = diffing.field_diff(a_snap, b_snap, b_snap)
    return {
        "from_revision_id": str(a.id),
        "to_revision_id": str(b.id),
        "body_diff": diffing.body_diff(a.markdown, b.markdown, from_label="from", to_label="to"),
        "field_diff": fields,
    }


def list_revisions(
    session: Session, user_id: uuid.UUID, post_id: uuid.UUID, limit: int = 100
) -> list[PostRevision]:
    """Newest-first revision timeline for a post (ownership-checked)."""
    get_post(session, user_id, post_id)  # ownership + existence
    return list(
        session.scalars(
            select(PostRevision)
            .where(PostRevision.post_id == post_id, PostRevision.user_id == user_id)
            .order_by(PostRevision.created_at.desc())
            .limit(limit)
        ).all()
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


# ---------------------------------------------------------------------------
# Ordered merge (spec 005, US6, T118)
# ---------------------------------------------------------------------------


def merge_posts(
    session: Session,
    user_id: uuid.UUID,
    primary_id: uuid.UUID,
    secondary_id: uuid.UUID,
    *,
    order: str = "primary_first",
    title: str | None = None,
    current_version: int,
) -> Post:
    """Merge *secondary* into *primary* in a chosen order, losing no sources.

    The two bodies are concatenated in ``order``; the result becomes a new
    ``merge`` revision on the primary. The secondary's capture sources are
    re-parented to the primary (so no source is lost) and a ``merged_from``
    relation records provenance. The secondary is marked ``discarded`` — kept and
    recoverable, never hard-deleted. Uses the primary's optimistic version lock.
    """
    from app.models.blog import PostSource

    if primary_id == secondary_id:
        raise ValidationError("Cannot merge a post with itself", code="merge_self")
    primary = get_post(session, user_id, primary_id)
    secondary = get_post(session, user_id, secondary_id)
    if primary.version != current_version:
        raise VersionConflictError("Post was modified; refresh", code="version_conflict")

    if order == "secondary_first":
        merged = f"{secondary.markdown}\n\n---\n\n{primary.markdown}"
    else:
        merged = f"{primary.markdown}\n\n---\n\n{secondary.markdown}"

    primary.markdown = merged
    if title:
        primary.title = title
    primary.version += 1

    # Re-parent the secondary's sources so the merged article keeps them all.
    for src in session.scalars(select(PostSource).where(PostSource.post_id == secondary_id)).all():
        src.post_id = primary_id

    rev = _new_revision(
        session,
        primary,
        merged,
        "merge",
        primary.current_revision_id,
        change_summary=f"合并自 {secondary_id}",
    )
    rev.applied_at = datetime.now(UTC)
    primary.current_revision_id = rev.id

    session.add(
        EntityRelation(
            id=uuid.uuid4(),
            user_id=user_id,
            source_type="post",
            source_id=primary_id,
            target_type="post",
            target_id=secondary_id,
            relation_type="derived_from",
            metadata_json={"merge": True, "order": order},
        )
    )
    # The secondary is retained but removed from active lists (recoverable).
    secondary.content_status = "discarded"
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="post.merged",
            entity_type="post",
            entity_id=primary_id,
            after_summary_json={"merged_from": str(secondary_id), "order": order},
        )
    )
    return primary


# ---------------------------------------------------------------------------
# Itemized batch operations (spec 005, US6, T119)
# ---------------------------------------------------------------------------

_BATCH_OPS = ("set_class", "set_status", "set_category", "add_tags", "archive", "discard")


def batch_operation(
    session: Session,
    user_id: uuid.UUID,
    post_ids: list[uuid.UUID],
    op: str,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Apply *op* to each post independently — one failure never rolls back the rest.

    Each item runs in its own SAVEPOINT; a failing item is reported with its error
    and the batch continues. Returns a per-item result list preserving input order.
    """
    if op not in _BATCH_OPS:
        raise ValidationError(f"Unknown batch op '{op}'", code="invalid_batch_op")
    params = params or {}
    results: list[dict[str, Any]] = []
    for pid in post_ids:
        try:
            with session.begin_nested():
                post = get_post(session, user_id, pid)
                _apply_batch_op(session, user_id, post, op, params)
            results.append({"id": str(pid), "ok": True})
        except Exception as exc:
            code = getattr(exc, "code", None) or exc.__class__.__name__
            results.append({"id": str(pid), "ok": False, "error": code})
    return results


def _apply_batch_op(
    session: Session, user_id: uuid.UUID, post: Post, op: str, params: dict[str, Any]
) -> None:
    if op == "set_class":
        value = params.get("content_class")
        if not value:
            raise ValidationError("content_class required", code="missing_param")
        post.content_class = value
    elif op == "set_status":
        value = params.get("content_status")
        if not value:
            raise ValidationError("content_status required", code="missing_param")
        post.content_status = value
    elif op == "set_category":
        category_id = params.get("category_id")
        if category_id:
            from app.models.blog import PostCategoryProfile
            from app.models.foundation import Category

            category_uuid = uuid.UUID(category_id) if isinstance(category_id, str) else category_id
            category = session.scalar(
                select(Category).where(
                    Category.id == category_uuid,
                    Category.user_id == user_id,
                    Category.kind == "post",
                )
            )
            profile = session.get(PostCategoryProfile, category_uuid)
            if category is None or profile is None or profile.user_id != user_id:
                raise ValidationError("category_id not found", code="invalid_category")
            if not profile.enabled:
                raise ValidationError("category is disabled", code="category_disabled")
            post.category_id = category_uuid
        else:
            post.category_id = None
    elif op == "add_tags":
        from app.models.posts import PostTag

        existing = set(
            session.scalars(select(PostTag.tag_id).where(PostTag.post_id == post.id)).all()
        )
        for tid in params.get("tag_ids", []):
            tid_u = uuid.UUID(tid) if isinstance(tid, str) else tid
            if tid_u not in existing:
                session.add(PostTag(post_id=post.id, user_id=user_id, tag_id=tid_u))
    elif op == "archive":
        post.content_status = "archived"
    elif op == "discard":
        post.content_status = "discarded"
    post.version += 1
