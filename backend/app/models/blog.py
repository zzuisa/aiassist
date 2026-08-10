"""Blog content-management models (spec 005): capture sources, content types,
taxonomy profiles/aliases/keywords/merges, Skills + versions + defaults, AI runs/
candidates/decisions, settings and word-cloud snapshots. All additive."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk


def _fk_user() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


class PostSource(Base, TimestampMixin):
    __tablename__ = "post_sources"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    post_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="saved")
    detected_format: Mapped[str | None] = mapped_column(String(12))
    original_url: Mapped[str | None] = mapped_column(Text)
    source_site: Mapped[str | None] = mapped_column(String(240))
    source_author: Mapped[str | None] = mapped_column(String(240))
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original_title: Mapped[str | None] = mapped_column(Text)
    original_text: Mapped[str | None] = mapped_column(Text)
    normalized_markdown: Mapped[str | None] = mapped_column(Text)
    user_note: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Stable external identity for imports.  JSON metadata remains available
    # for provider-specific details, while these columns support real database
    # idempotency and safe concurrent migration runs.
    external_system: Mapped[str | None] = mapped_column(String(32))
    external_record_id: Mapped[str | None] = mapped_column(String(128))
    external_task_id: Mapped[str | None] = mapped_column(String(128))
    snapshot_object_key: Mapped[str | None] = mapped_column(String(512))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    fetch_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    async_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "source_type in ('blank','clipboard','url','quick','template','file')",
            name="post_source_type",
        ),
        CheckConstraint(
            "status in ('saved','pending','processing','partial','completed','failed','cancelled')",
            name="post_source_status",
        ),
        CheckConstraint(
            "source_type <> 'url' or original_url is not null", name="post_source_url_required"
        ),
        Index("ix_post_sources_user_status", "user_id", "status", "created_at"),
        Index("ix_post_sources_user_post", "user_id", "post_id", "created_at"),
        Index(
            "uq_post_sources_external_record",
            "user_id",
            "external_system",
            "external_record_id",
            unique=True,
            postgresql_where=text("external_system is not null and external_record_id is not null"),
        ),
        Index(
            "ix_post_sources_user_url",
            "user_id",
            "original_url",
            postgresql_where=text("original_url is not null"),
        ),
    )


class PostContentType(Base, TimestampMixin):
    __tablename__ = "post_content_types"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    content_class: Mapped[str] = mapped_column(String(16), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    field_schema_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_system_seed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_content_type_user_key"),)


class PostCategoryProfile(Base):
    __tablename__ = "post_category_profiles"
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = _fk_user()
    parent_category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    description: Mapped[str | None] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PostTagProfile(Base):
    __tablename__ = "post_tag_profiles"
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = _fk_user()
    color: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PostTagAlias(Base):
    __tablename__ = "post_tag_aliases"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        Index("uq_tag_alias_user_alias_ci", "user_id", text("lower(alias)"), unique=True),
    )


class PostKeyword(Base, TimestampMixin):
    __tablename__ = "post_keywords"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    canonical_text: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_stop_word: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("user_id", "canonical_text", name="uq_keyword_user_text"),)


class PostKeywordAlias(Base):
    __tablename__ = "post_keyword_aliases"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("post_keywords.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(120), nullable=False)
    __table_args__ = (
        Index("uq_keyword_alias_user_alias_ci", "user_id", text("lower(alias)"), unique=True),
    )


class PostKeywordLink(Base):
    __tablename__ = "post_keyword_links"
    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("post_keywords.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = _fk_user()
    source: Mapped[str] = mapped_column(String(12), nullable=False, default="user")
    weight: Mapped[float | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "source in ('user','ai','recomputed','import')",
            name="keyword_link_source",
        ),
        Index("ix_post_keyword_links_user_keyword_post", "user_id", "keyword_id", "post_id"),
    )


class TaxonomyMerge(Base, TimestampMixin):
    __tablename__ = "post_taxonomy_merges"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    affected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    async_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    error_summary: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (
        CheckConstraint("kind in ('category','tag','keyword')", name="taxonomy_merge_kind"),
    )


class BlogSkill(Base, TimestampMixin):
    __tablename__ = "blog_skills"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index(
            "uq_blog_skill_name",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at is null"),
        ),
    )


class BlogSkillVersion(Base):
    __tablename__ = "blog_skill_versions"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blog_skills.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    schema_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="blog-skill-config.v1"
    )
    recommended_model: Mapped[str | None] = mapped_column(String(120))
    max_content_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=200000)
    long_content_strategy: Mapped[str] = mapped_column(String(24), nullable=False, default="reject")
    change_summary: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("skill_id", "version_number", name="uq_skill_version_number"),
        CheckConstraint(
            "long_content_strategy in ('reject','chunk','summarize_then_process')",
            name="skill_version_strategy",
        ),
    )


class BlogSkillDefault(Base, TimestampMixin):
    __tablename__ = "blog_skill_defaults"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blog_skills.id", ondelete="CASCADE"), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("user_id", "scope_type", "scope_key", name="uq_skill_default_scope"),
        CheckConstraint(
            "scope_type in ('global','content_class','content_type')", name="skill_default_scope"
        ),
    )


class PostAIRun(Base):
    __tablename__ = "post_ai_runs"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    async_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    base_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    optimization_type: Mapped[str] = mapped_column(String(16), nullable=False)
    content_class: Mapped[str] = mapped_column(String(16), nullable=False)
    content_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    skill_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(32), nullable=False, default="radio")
    model_key: Mapped[str] = mapped_column(String(120), nullable=False)
    ai_schema_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="blog-optimization.v1"
    )
    field_policy_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    protected_tokens_json: Mapped[dict | None] = mapped_column(JSONB)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    outcome: Mapped[str | None] = mapped_column(String(12))
    validation_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("async_job_id", name="uq_ai_run_job"),
        CheckConstraint("provider_key in ('radio','aiassist')", name="ai_run_provider"),
        Index("ix_ai_runs_user_post", "user_id", "post_id", "created_at"),
    )


class PostAICandidate(Base):
    __tablename__ = "post_ai_candidates"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    ai_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("post_ai_runs.id", ondelete="CASCADE"), nullable=False
    )
    base_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    candidate_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    field_diff_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    validation_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    applied_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("ai_run_id", name="uq_candidate_run"),
        CheckConstraint(
            "status in ('pending','merge_required','applied','rejected','copied')",
            name="candidate_status",
        ),
    )


class PostCandidateDecision(Base):
    __tablename__ = "post_candidate_decisions"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("post_ai_candidates.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    selected_fields_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    rejected_fields_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    current_revision_before_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    result_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "action in ('apply_all','apply_body','apply_metadata','apply_fields',"
            "'keep_current','reject','copy')",
            name="candidate_decision_action",
        ),
    )


class BlogSettings(Base, TimestampMixin):
    __tablename__ = "blog_settings"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    schema_version: Mapped[str] = mapped_column(
        String(24), nullable=False, default="blog-settings.v1"
    )
    create_defaults_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    clipboard_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    url_capture_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ai_apply_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    word_cloud_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PostWordCloudSnapshot(Base):
    __tablename__ = "post_word_cloud_snapshots"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _fk_user()
    source_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    filter_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    filter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    terms_json: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="ready")
    async_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("user_id", "source_kind", "filter_hash", name="uq_wordcloud_scope"),
        CheckConstraint("source_kind in ('tag','keyword')", name="wordcloud_source_kind"),
    )
