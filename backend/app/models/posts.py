"""Post, immutable revision, and post-tag models.

AI-generated revisions are created without changing ``current_revision_id``;
applying a revision is an explicit user action. Public read is gated by
``status == 'published'`` and a globally-unique slug. Blog content-management
(spec 005) adds additive projection columns and a full snapshot on each revision.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk

_CONTENT_STATUS = (
    "pending_capture,pending_parse,triage,draft,ai_queued,ai_processing,"
    "ai_review,merge_required,completed,archived,discarded"
)
_CONTENT_CLASS = "technical,project,learning,life,travel,diary,essay,bookmark,media,item,quick"


class Post(Base, TimestampMixin):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str | None] = mapped_column(String(240))
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cover_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    seo_title: Mapped[str | None] = mapped_column(String(70))
    seo_description: Mapped[str | None] = mapped_column(String(180))
    excerpt: Mapped[str | None] = mapped_column(String(400))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- spec 005: additive blog content-management projection ---
    subtitle: Mapped[str | None] = mapped_column(String(240))
    summary: Mapped[str | None] = mapped_column(Text)
    content_status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    content_class: Mapped[str] = mapped_column(String(16), nullable=False, default="essay")
    content_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-CN")
    editor_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="rich", server_default="rich"
    )
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location_text: Mapped[str | None] = mapped_column(String(240))
    project_text: Mapped[str | None] = mapped_column(String(240))
    structured_data_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    latest_ai_status: Mapped[str | None] = mapped_column(String(24))
    first_ai_optimized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ai_optimized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_optimization_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_skill_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        CheckConstraint("status in ('draft','private','published')", name="post_status"),
        CheckConstraint(
            "content_status in ('pending_capture','pending_parse','triage','draft',"
            "'ai_queued','ai_processing','ai_review','merge_required','completed',"
            "'archived','discarded')",
            name="post_content_status",
        ),
        CheckConstraint(
            "content_class in ('technical','project','learning','life','travel',"
            "'diary','essay','bookmark','media','item','quick')",
            name="post_content_class",
        ),
        CheckConstraint("editor_mode in ('markdown','rich','split')", name="post_editor_mode"),
        CheckConstraint("ai_optimization_count >= 0", name="post_ai_count_nonneg"),
        Index(
            "uq_posts_published_slug",
            "slug",
            unique=True,
            postgresql_where=text("status = 'published' AND deleted_at IS NULL"),
        ),
        Index("ix_posts_user_id_status", "user_id", "status"),
        Index("ix_posts_user_content_status", "user_id", "content_status", "updated_at"),
        Index("ix_posts_user_content_class", "user_id", "content_class", "content_type_id"),
    )


class PostRevision(Base):
    __tablename__ = "post_revisions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    parent_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    base_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="user_edit")
    revision_number: Mapped[int | None] = mapped_column(Integer)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    change_summary: Mapped[str | None] = mapped_column(String(500))
    llm_log_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    async_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    skill_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    schema_version: Mapped[str] = mapped_column(
        String(24), nullable=False, default="post-revision.v1"
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "source in ('user','ai','capture','user_edit','ai_candidate',"
            "'ai_applied','restore','import','merge')",
            name="post_revision_source",
        ),
        Index("ix_post_revisions_post_id", "post_id", "created_at"),
        Index(
            "uq_post_revisions_number",
            "post_id",
            "revision_number",
            unique=True,
            postgresql_where=text("revision_number IS NOT NULL"),
        ),
    )


class PostTag(Base):
    __tablename__ = "post_tags"

    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
