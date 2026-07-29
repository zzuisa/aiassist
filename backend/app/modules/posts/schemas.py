"""Blog post request / response DTOs (spec 005, T018).

Pulls the Pydantic models out of the router and adds the full blog-content-
management surface: content_status, content_class, content_type_id, language,
structured_data, and revision snapshots.  The router imports from here; the old
in-router classes are retained as thin re-exports until callers are updated.

All response models use ``model_config = {"extra": "forbid"}`` to guard against
accidental field leakage and to satisfy the OpenAPI strict contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Constants — mirror data-model.md enumerations
# ---------------------------------------------------------------------------

CONTENT_STATUSES = (
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
)

CONTENT_CLASSES = (
    "technical",
    "project",
    "learning",
    "life",
    "travel",
    "diary",
    "essay",
    "bookmark",
    "media",
    "item",
    "quick",
)

REVISION_SOURCES = (
    "capture",
    "user_edit",
    "ai_candidate",
    "ai_applied",
    "restore",
    "import",
    "merge",
    # legacy values from pre-005 schema
    "user",
    "ai",
)

# ---------------------------------------------------------------------------
# Request DTOs
# ---------------------------------------------------------------------------


class PostCreate(BaseModel):
    """Create a new post (blank path). Must remain backward-compatible."""

    model_config = {"extra": "forbid"}
    title: str = Field(min_length=1, max_length=240)
    markdown: str = Field(max_length=200_000)
    content_class: str = Field(default="essay", max_length=16)
    language: str = Field(default="zh-CN", max_length=16)
    source_refs: list[dict] = Field(default_factory=list)
    version: int | None = None


class PostPatch(BaseModel):
    """Partial update — only supplied fields are applied (PATCH semantics)."""

    model_config = {"extra": "forbid"}
    title: str | None = Field(default=None, min_length=1, max_length=240)
    markdown: str | None = Field(default=None, max_length=200_000)
    content_class: str | None = Field(default=None, max_length=16)
    content_type_id: uuid.UUID | None = None
    language: str | None = Field(default=None, max_length=16)
    structured_data: dict[str, Any] | None = None
    version: int | None = None


class GenerateBody(BaseModel):
    """Legacy AI generation request (pre-005 blog.generate job)."""

    model_config = {"extra": "forbid"}
    scenario: str = Field(pattern="^(generate_blog|optimize_blog|translate_blog)$")
    source_refs: list[dict] = Field(default_factory=list, max_length=50)
    instruction: str | None = Field(default=None, max_length=2000)


class PublishBody(BaseModel):
    model_config = {"extra": "forbid"}
    published: bool
    version: int


class RestoreRevisionBody(BaseModel):
    """Restore a past revision as a new user_edit revision."""

    model_config = {"extra": "forbid"}
    version: int  # optimistic lock — must match current post.version


# ---------------------------------------------------------------------------
# Snapshot DTO — the full storable/restorable post state
# ---------------------------------------------------------------------------


class PostSnapshot(BaseModel):
    """Complete, restorable post state stored in PostRevision.snapshot_json.

    Every user-edit or AI-applied save writes one of these into the revision.
    A restore reads it back and applies selected fields onto the current Post.
    The schema_version field guards against future field additions.
    """

    model_config = {"extra": "forbid"}
    schema_version: Literal["post-revision.v1"] = "post-revision.v1"
    title: str
    markdown: str
    content_class: str
    content_type_id: str | None = None
    language: str
    structured_data: dict[str, Any] = Field(default_factory=dict)
    # Optional enrichment (present on ai_applied revisions).
    summary: str | None = None
    subtitle: str | None = None


# ---------------------------------------------------------------------------
# Response DTOs
# ---------------------------------------------------------------------------


class PostOut(BaseModel):
    """Private post response — full internal projection."""

    model_config = {"extra": "forbid"}
    id: str
    title: str
    subtitle: str | None
    summary: str | None
    markdown: str
    status: str
    slug: str | None
    content_status: str
    content_class: str
    content_type_id: str | None
    language: str
    structured_data: dict[str, Any]
    version: int
    current_revision_id: str | None
    created_at: str
    updated_at: str
    published_at: str | None


class RevisionOut(BaseModel):
    """Summary of a single PostRevision (no full markdown for list views)."""

    model_config = {"extra": "forbid"}
    id: str
    post_id: str
    source: str
    version: int
    change_summary: str | None
    created_at: str
    applied_at: str | None


class RevisionDetailOut(RevisionOut):
    """Full revision including snapshot fields (for diff / restore flows)."""

    model_config = {"extra": "forbid"}
    snapshot: PostSnapshot | None


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

from app.models.posts import Post, PostRevision  # noqa: E402 (local import avoids circular)


def post_out(p: Post) -> PostOut:
    return PostOut(
        id=str(p.id),
        title=p.title,
        subtitle=getattr(p, "subtitle", None),
        summary=getattr(p, "summary", None),
        markdown=p.markdown,
        status=p.status,
        slug=p.slug,
        content_status=getattr(p, "content_status", "draft"),
        content_class=getattr(p, "content_class", "essay"),
        content_type_id=str(p.content_type_id) if getattr(p, "content_type_id", None) else None,
        language=getattr(p, "language", "zh-CN"),
        structured_data=getattr(p, "structured_data_json", {}) or {},
        version=p.version,
        current_revision_id=str(p.current_revision_id) if p.current_revision_id else None,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
        published_at=p.published_at.isoformat() if p.published_at else None,
    )


def revision_out(r: PostRevision, *, include_snapshot: bool = False) -> RevisionOut | RevisionDetailOut:
    base = dict(
        id=str(r.id),
        post_id=str(r.post_id),
        source=r.source,
        version=getattr(r, "version", 0),
        change_summary=getattr(r, "change_summary", None),
        created_at=r.created_at.isoformat(),
        applied_at=r.applied_at.isoformat() if r.applied_at else None,
    )
    if include_snapshot:
        snap_data = getattr(r, "snapshot_json", None)
        snapshot = PostSnapshot.model_validate(snap_data) if snap_data else None
        return RevisionDetailOut(**base, snapshot=snapshot)
    return RevisionOut(**base)
