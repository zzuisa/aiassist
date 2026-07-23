"""Search document model for the derived cross-entity index (US7).

Committed business data is always searched directly; this table is an async
derived accelerator, never an authorization boundary. Ownership is re-checked on
every read and public posts use post.status, not the presence of a document.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SearchDocument(Base):
    __tablename__ = "search_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    tags_text: Mapped[str | None] = mapped_column(Text)
    category_text: Mapped[str | None] = mapped_column(Text)
    metadata_text: Mapped[str | None] = mapped_column(Text)
    document_tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    thumbnail_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    entity_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "entity_type", "entity_id", name="uq_search_documents_user_entity"
        ),
        Index("ix_search_documents_tsv", "document_tsv", postgresql_using="gin"),
        Index("ix_search_documents_user_type", "user_id", "entity_type"),
    )
