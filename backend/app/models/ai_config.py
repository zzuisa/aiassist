"""Versioned, user-owned configuration for LLM module behaviour.

Only editable instructions and tool defaults live here.  Permissions, schemas,
confirmation requirements and provider credentials remain application policy.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk


class AIConfigProfile(Base, TimestampMixin):
    __tablename__ = "ai_config_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    module_key: Mapped[str] = mapped_column(String(80), nullable=False)
    active_prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_prompt_versions.id", ondelete="SET NULL")
    )
    active_skill_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_skill_versions.id", ondelete="SET NULL")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "module_key", name="uq_ai_config_profile_user_module"),
    )


class AIPromptVersion(Base):
    __tablename__ = "ai_prompt_versions"

    id: Mapped[uuid.UUID] = uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_config_profiles.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "profile_id", "version_number", name="uq_ai_prompt_version_profile_number"
        ),
        Index("ix_ai_prompt_versions_profile", "profile_id"),
    )


class AISkillVersion(Base):
    __tablename__ = "ai_skill_versions"

    id: Mapped[uuid.UUID] = uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_config_profiles.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    allowed_tool_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    parameter_defaults: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_guidance: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("profile_id", "version_number", name="uq_ai_skill_version_profile_number"),
        Index("ix_ai_skill_versions_profile", "profile_id"),
    )


class AIConfigBinding(Base):
    """Immutable record of the effective configuration used for one AI call."""

    __tablename__ = "ai_config_bindings"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    module_key: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_prompt_versions.id", ondelete="SET NULL")
    )
    skill_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_skill_versions.id", ondelete="SET NULL")
    )
    model_key: Mapped[str] = mapped_column(String(120), nullable=False, default="scenario-default")
    run_reference: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_ai_config_bindings_user_module_created", "user_id", "module_key", "created_at"),
    )
