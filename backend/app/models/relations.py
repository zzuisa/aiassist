"""Single shared entity_relations model + same-user relation service.

Owned by US5 (T081) but used by every module (voice confirm, capture convert,
blog sources). Relations are typed and always within a single user; a service
helper validates both ends belong to the user before creating one.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, uuid_pk

RELATION_TYPES = (
    "derived_from",
    "related_to",
    "converted_to",
    "material_for",
    "generated_by",
    "duplicate_of",
)


class EntityRelation(Base):
    __tablename__ = "entity_relations"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(24), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "relation_type in ('derived_from','related_to','converted_to',"
            "'material_for','generated_by','duplicate_of')",
            name="entity_relation_type",
        ),
        UniqueConstraint(
            "user_id",
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "relation_type",
            name="uq_entity_relations_unique",
        ),
        Index("ix_entity_relations_user_source", "user_id", "source_type", "source_id"),
    )
