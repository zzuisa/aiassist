"""Capture, capture-asset, and AI-tag models (US5).

User-provided facts and AI suggestions are stored in separate columns; AI never
writes ``*_user`` columns. Assets keep an internal storage_key never returned to
clients. The raw original is never overwritten by derived processing.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk

CAPTURE_TYPES = (
    "item",
    "inspiration",
    "note",
    "image",
    "document",
    "link",
    "location",
    "purchase",
    "blog_material",
)


class Capture(Base, TimestampMixin):
    __tablename__ = "captures"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(24), nullable=False, default="item")
    # User-provided facts.
    title_user: Mapped[str | None] = mapped_column(String(240))
    description_user: Mapped[str | None] = mapped_column(Text)
    brand_user: Mapped[str | None] = mapped_column(String(120))
    model_user: Mapped[str | None] = mapped_column(String(120))
    material_user: Mapped[str | None] = mapped_column(String(120))
    color_user: Mapped[str | None] = mapped_column(String(80))
    storage_location_user: Mapped[str | None] = mapped_column(String(240))
    # AI suggestions (never overwrite *_user).
    title_ai: Mapped[str | None] = mapped_column(String(240))
    description_ai: Mapped[str | None] = mapped_column(Text)
    brand_ai: Mapped[str | None] = mapped_column(String(120))
    model_ai: Mapped[str | None] = mapped_column(String(120))
    material_ai: Mapped[str | None] = mapped_column(String(120))
    color_ai: Mapped[str | None] = mapped_column(String(80))
    storage_location_ai: Mapped[str | None] = mapped_column(String(240))
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    category_ai_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purchase_place: Mapped[str | None] = mapped_column(String(240))
    purchase_price: Mapped[float | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    usage_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    ocr_text: Mapped[str | None] = mapped_column(Text)
    ai_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    processing_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    possible_duplicate_of: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "type in ('item','inspiration','note','image','document','link',"
            "'location','purchase','blog_material')",
            name="capture_type",
        ),
        CheckConstraint(
            "processing_status in ('pending','processing','ready','needs_input','failed')",
            name="capture_processing_status",
        ),
        Index("ix_captures_user_id_type", "user_id", "type"),
        Index("ix_captures_user_id_deleted_at", "user_id", "deleted_at"),
    )


class CaptureAsset(Base):
    __tablename__ = "capture_assets"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    capture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("captures.id", ondelete="CASCADE"), nullable=False
    )
    upload_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="original")
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    bucket: Mapped[str | None] = mapped_column(String(120))
    media_type: Mapped[str | None] = mapped_column(String(120))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    exif_json_sanitized: Mapped[dict | None] = mapped_column(JSONB)
    gps_removed: Mapped[bool] = mapped_column(nullable=False, default=False)
    processing_version: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="uploading")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "role in ('original','thumbnail','preview','attachment','audio')",
            name="capture_asset_role",
        ),
        CheckConstraint(
            "status in ('uploading','ready','failed','deleted')", name="capture_asset_status"
        ),
        Index("ix_capture_assets_user_id_sha256", "user_id", "sha256"),
        Index("ix_capture_assets_capture_id", "capture_id"),
    )


class CaptureAiTag(Base):
    __tablename__ = "capture_ai_tags"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    capture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("captures.id", ondelete="CASCADE"), nullable=False
    )
    tag_name: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CaptureTag(Base):
    __tablename__ = "capture_tags"

    capture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("captures.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
