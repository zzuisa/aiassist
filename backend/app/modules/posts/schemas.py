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


_UNSET = object()


class PostPatch(BaseModel):
    """Partial update — only supplied fields are applied (PATCH semantics).

    ``version`` is required (optimistic lock).  Nullable fields use a sentinel so
    an explicit ``null`` (clear the field) is distinguishable from "omitted".
    """

    model_config = {"extra": "forbid"}
    version: int
    title: str | None = Field(default=None, min_length=1, max_length=240)
    subtitle: str | None = Field(default=None, max_length=240)
    summary: str | None = Field(default=None, max_length=2000)
    markdown: str | None = Field(default=None, max_length=200_000)
    content_status: str | None = Field(default=None, max_length=24)
    content_class: str | None = Field(default=None, max_length=32)
    content_type_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    keyword_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=16)
    editor_mode: str | None = Field(default=None, pattern="^(markdown|rich|split)$")
    occurred_at: datetime | None = None
    location: str | None = Field(default=None, max_length=240)
    project: str | None = Field(default=None, max_length=240)
    structured_data: dict[str, Any] | None = None

    def provided_fields(self) -> set[str]:
        """Field names the client actually sent (excludes version)."""
        return set(self.model_fields_set) - {"version"}


# ---------------------------------------------------------------------------
# Content-type DTOs (spec 005, US2)
# ---------------------------------------------------------------------------


class ContentTypeWrite(BaseModel):
    model_config = {"extra": "forbid"}
    content_class: str = Field(max_length=32)
    key: str = Field(pattern="^[a-z][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    field_schema: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    enabled: bool = True


class ContentTypeOut(BaseModel):
    model_config = {"extra": "forbid"}
    id: str
    content_class: str
    key: str
    name: str
    description: str | None
    field_schema: dict[str, Any]
    sort_order: int
    enabled: bool
    schema_version: int
    created_at: str
    updated_at: str


class TaxonomyWrite(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    parent_id: uuid.UUID | None = None
    aliases: list[str] = Field(default_factory=list, max_length=50)
    color: str | None = Field(default=None, max_length=32)
    enabled: bool = True
    stop_word: bool = False


class TaxonomyItemOut(BaseModel):
    model_config = {"extra": "forbid"}
    id: str
    kind: str
    name: str
    description: str | None
    parent_id: str | None
    aliases: list[str]
    color: str | None
    enabled: bool
    stop_word: bool
    usage_count: int


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


class OptimizeBody(BaseModel):
    """Submit an AI optimization bound to the current revision (openapi OptimizationRequest)."""

    model_config = {"extra": "forbid"}
    post_version: int = Field(ge=1)
    optimization_type: str = Field(pattern="^(full|language|structure|metadata|check|reoptimize)$")
    scope: str = Field(default="all", pattern="^(all|body|metadata|selected_fields)$")
    selected_fields: list[str] = Field(default_factory=list, max_length=200)
    skill_id: uuid.UUID | None = None
    provider_key: str | None = Field(default=None, pattern="^(radio|aiassist)$")
    model_key: str | None = Field(default=None, max_length=120)
    instruction: str | None = Field(default=None, max_length=2000)
    request_nonce: str | None = Field(default=None, max_length=64)


class CandidateDecisionBody(BaseModel):
    """Apply a terminal decision to an AI candidate (spec 005, US4)."""

    model_config = {"extra": "forbid"}
    post_version: int = Field(ge=1)
    action: str = Field(
        pattern="^(apply_all|apply_body|apply_metadata|apply_fields|keep_current|reject|copy)$"
    )
    selected_fields: list[str] = Field(default_factory=list, max_length=200)


# ---------------------------------------------------------------------------
# Skill management DTOs (spec 005, US5)
# ---------------------------------------------------------------------------


class SkillCreateBody(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    config: dict[str, Any] | None = None
    recommended_model: str | None = Field(default=None, max_length=120)
    max_content_chars: int = Field(default=200_000, ge=1000, le=200_000)
    long_content_strategy: str = Field(
        default="reject", pattern="^(reject|chunk|summarize_then_process)$"
    )


class SkillMetaBody(BaseModel):
    model_config = {"extra": "forbid"}
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class SkillEnableBody(BaseModel):
    model_config = {"extra": "forbid"}
    enabled: bool


class SkillVersionBody(BaseModel):
    model_config = {"extra": "forbid"}
    config: dict[str, Any]
    recommended_model: str | None = Field(default=None, max_length=120)
    max_content_chars: int = Field(default=200_000, ge=1000, le=200_000)
    long_content_strategy: str = Field(
        default="reject", pattern="^(reject|chunk|summarize_then_process)$"
    )
    change_summary: str | None = Field(default=None, max_length=500)


class SkillDefaultBody(BaseModel):
    model_config = {"extra": "forbid"}
    scope_type: str = Field(pattern="^(global|content_class|content_type)$")
    scope_key: str = Field(min_length=1, max_length=64)
    skill_id: uuid.UUID


# ---------------------------------------------------------------------------
# Article management DTOs (spec 005, US6)
# ---------------------------------------------------------------------------


class MergeBody(BaseModel):
    model_config = {"extra": "forbid"}
    primary_id: uuid.UUID
    secondary_id: uuid.UUID
    primary_version: int = Field(ge=1)
    order: str = Field(default="primary_first", pattern="^(primary_first|secondary_first)$")
    title: str | None = Field(default=None, max_length=240)


class BatchBody(BaseModel):
    model_config = {"extra": "forbid"}
    post_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    op: str = Field(pattern="^(set_class|set_status|set_category|add_tags|archive|discard)$")
    params: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Capture request DTOs (spec 005, US1) — mirror openapi ClipboardCapture etc.
# ---------------------------------------------------------------------------

_DETECTED_FORMATS = ("plain", "markdown", "html", "rich", "url", "code", "image", "mixed")
_URL_USAGES = (
    "bookmark",
    "summary_note",
    "reading_note",
    "technical_material",
    "travel_material",
    "personal_article",
    "triage",
)


class BlankCaptureBody(BaseModel):
    model_config = {"extra": "forbid"}
    title: str = Field(default="未命名", max_length=240)
    content_class: str = Field(default="essay", max_length=32)
    content_type_id: uuid.UUID | None = None
    language: str = Field(default="zh-CN", max_length=16)


class ClipboardCaptureBody(BaseModel):
    model_config = {"extra": "forbid"}
    raw_content: str = Field(min_length=1, max_length=2_097_152)
    normalized_markdown: str | None = Field(default=None, max_length=200_000)
    detected_format: str = Field(pattern="^(plain|markdown|html|rich|url|code|image|mixed)$")
    content_class: str = Field(default="quick", max_length=32)
    content_type_id: uuid.UUID | None = None
    ai_enabled: bool = False
    skill_id: uuid.UUID | None = None
    save_as_defaults: bool = False


class UrlCaptureBody(BaseModel):
    model_config = {"extra": "forbid"}
    url: str = Field(min_length=1, max_length=4096)
    note: str | None = Field(default=None, max_length=10000)
    usage: str = Field(
        default="triage",
        pattern=(
            "^(bookmark|summary_note|reading_note|technical_material|"
            "travel_material|personal_article|triage)$"
        ),
    )
    content_class: str = Field(default="bookmark", max_length=32)
    content_type_id: uuid.UUID | None = None
    ai_enabled: bool = False
    skill_id: uuid.UUID | None = None
    save_as_defaults: bool = False


class QuickCaptureBody(BaseModel):
    model_config = {"extra": "forbid"}
    content: str = Field(min_length=1, max_length=20000)
    content_class: str = Field(default="quick", max_length=32)
    ai_enabled: bool = False
    save_and_continue: bool = False


# ---------------------------------------------------------------------------
# Capture response DTOs
# ---------------------------------------------------------------------------


class PostSourceOut(BaseModel):
    """Owned source metadata + bounded original content (openapi PostSource)."""

    model_config = {"extra": "forbid"}
    id: str
    post_id: str | None
    source_type: str
    status: str
    detected_format: str | None
    original_url: str | None
    original_title: str | None
    source_site: str | None
    source_author: str | None
    source_published_at: str | None
    original_text: str | None
    normalized_markdown: str | None
    user_note: str | None
    metadata: dict[str, Any]
    external_system: str | None
    external_record_id: str | None
    external_task_id: str | None
    has_snapshot: bool
    attempt_count: int
    captured_at: str | None
    error: dict[str, Any] | None


class CaptureResultOut(BaseModel):
    """Durable capture result: post + source + optional job + warnings."""

    model_config = {"extra": "forbid"}
    post: PostOut
    source: PostSourceOut
    job: dict[str, Any] | None
    warnings: list[str]


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


class PostSourceSummary(BaseModel):
    """Compact source descriptor embedded in a post's source_summary."""

    model_config = {"extra": "forbid"}
    id: str
    source_type: str
    status: str
    original_url: str | None = None
    original_title: str | None = None
    captured_at: str | None = None


class PostAiSummary(BaseModel):
    """Presentation-only AI status roll-up for a post (openapi PostAiSummary)."""

    model_config = {"extra": "forbid"}
    display_status: str | None
    optimization_count: int
    first_optimized_at: str | None = None
    last_optimized_at: str | None = None
    latest_job_id: str | None = None
    pending_candidate_id: str | None = None


class PostOut(BaseModel):
    """Private post response — full internal projection (spec 005 US2)."""

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
    category_id: str | None = None
    tag_ids: list[str] = Field(default_factory=list)
    keyword_ids: list[str] = Field(default_factory=list)
    language: str
    editor_mode: str = "rich"
    occurred_at: str | None = None
    location: str | None = None
    project: str | None = None
    structured_data: dict[str, Any]
    source_summary: list[PostSourceSummary] = Field(default_factory=list)
    ai_summary: PostAiSummary | None = None
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


def _ai_summary(p: Post) -> PostAiSummary:
    first_optimized_at = p.first_ai_optimized_at
    last_optimized_at = p.last_ai_optimized_at
    return PostAiSummary(
        display_status=getattr(p, "latest_ai_status", None),
        optimization_count=getattr(p, "ai_optimization_count", 0) or 0,
        first_optimized_at=first_optimized_at.isoformat() if first_optimized_at else None,
        last_optimized_at=last_optimized_at.isoformat() if last_optimized_at else None,
    )


def post_out(p: Post) -> PostOut:
    """Lightweight projection (no relation queries) for lists and captures."""
    occurred_at = p.occurred_at
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
        category_id=str(p.category_id) if getattr(p, "category_id", None) else None,
        language=getattr(p, "language", "zh-CN"),
        editor_mode=getattr(p, "editor_mode", "rich"),
        occurred_at=occurred_at.isoformat() if occurred_at else None,
        location=getattr(p, "location_text", None),
        project=getattr(p, "project_text", None),
        structured_data=getattr(p, "structured_data_json", {}) or {},
        ai_summary=_ai_summary(p),
        version=p.version,
        current_revision_id=str(p.current_revision_id) if p.current_revision_id else None,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
        published_at=p.published_at.isoformat() if p.published_at else None,
    )


def post_detail_out(session: Any, p: Post) -> PostOut:
    """Full single-post projection: adds taxonomy relations and source summary."""
    from sqlalchemy import select

    from app.models.blog import PostKeywordLink, PostSource
    from app.models.posts import PostTag

    out = post_out(p)
    out.tag_ids = [
        str(t) for t in session.scalars(select(PostTag.tag_id).where(PostTag.post_id == p.id)).all()
    ]
    out.keyword_ids = [
        str(k)
        for k in session.scalars(
            select(PostKeywordLink.keyword_id).where(PostKeywordLink.post_id == p.id)
        ).all()
    ]
    sources = session.scalars(
        select(PostSource).where(PostSource.post_id == p.id).order_by(PostSource.created_at)
    ).all()
    out.source_summary = [
        PostSourceSummary(
            id=str(s.id),
            source_type=s.source_type,
            status=s.status,
            original_url=s.original_url,
            original_title=s.original_title,
            captured_at=s.captured_at.isoformat() if s.captured_at else None,
        )
        for s in sources
    ]
    return out


def content_type_out(ct: Any) -> ContentTypeOut:
    return ContentTypeOut(
        id=str(ct.id),
        content_class=ct.content_class,
        key=ct.key,
        name=ct.name,
        description=ct.description,
        field_schema=ct.field_schema_json or {},
        sort_order=ct.sort_order,
        enabled=ct.enabled,
        schema_version=ct.schema_version,
        created_at=ct.created_at.isoformat(),
        updated_at=ct.updated_at.isoformat(),
    )


def source_out(s: Any) -> PostSourceOut:
    meta = dict(getattr(s, "metadata_json", None) or {})
    error = None
    if s.error_code:
        error = {"code": s.error_code, "message": s.error_message or "", "retryable": True}
    return PostSourceOut(
        id=str(s.id),
        post_id=str(s.post_id) if s.post_id else None,
        source_type=s.source_type,
        status=s.status,
        detected_format=s.detected_format,
        original_url=s.original_url,
        original_title=s.original_title,
        source_site=s.source_site,
        source_author=s.source_author,
        source_published_at=s.source_published_at.isoformat() if s.source_published_at else None,
        original_text=s.original_text,
        normalized_markdown=s.normalized_markdown,
        user_note=s.user_note,
        metadata=meta,
        external_system=getattr(s, "external_system", None),
        external_record_id=getattr(s, "external_record_id", None),
        external_task_id=getattr(s, "external_task_id", None),
        has_snapshot=bool(s.snapshot_object_key),
        attempt_count=s.fetch_attempt_count,
        captured_at=s.captured_at.isoformat() if s.captured_at else None,
        error=error,
    )


def revision_out(
    r: PostRevision, *, include_snapshot: bool = False
) -> RevisionOut | RevisionDetailOut:
    base = {
        "id": str(r.id),
        "post_id": str(r.post_id),
        "source": r.source,
        "version": getattr(r, "version", 0),
        "change_summary": getattr(r, "change_summary", None),
        "created_at": r.created_at.isoformat(),
        "applied_at": r.applied_at.isoformat() if r.applied_at else None,
    }
    if include_snapshot:
        snap_data = getattr(r, "snapshot_json", None)
        snapshot = PostSnapshot.model_validate(snap_data) if snap_data else None
        return RevisionDetailOut(**base, snapshot=snapshot)
    return RevisionOut(**base)
