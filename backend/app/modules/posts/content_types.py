"""Content-class constants, content-type validation and per-user seeding (T020).

A ContentType gives a content_class a user-facing name plus an optional
field_schema_json (JSON Schema) for structured_data validation. System-seed
types are created once per user and never overwritten by a re-seed.
"""

from __future__ import annotations

import uuid
from typing import Any

import jsonschema
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models.blog import PostContentType

# ---------------------------------------------------------------------------
# Content-class registry
# ---------------------------------------------------------------------------

CONTENT_CLASSES: tuple[str, ...] = (
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

_CONTENT_CLASS_SET = frozenset(CONTENT_CLASSES)


def validate_content_class(value: str) -> None:
    if value not in _CONTENT_CLASS_SET:
        raise ValidationError(
            f"'{value}' is not a valid content_class. "
            f"Allowed: {', '.join(sorted(_CONTENT_CLASS_SET))}",
            code="invalid_content_class",
        )


# ---------------------------------------------------------------------------
# System-seed content types (one per class, minimal schema)
# ---------------------------------------------------------------------------

_SEED_TYPES: list[dict[str, Any]] = [
    {
        "content_class": "bookmark",
        "key": "system.bookmark.url",
        "name": "网址书签",
        "description": "保存网址和摘要",
        "field_schema_json": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "format": "uri"},
                "source_title": {"type": "string", "maxLength": 240},
            },
            "additionalProperties": True,
        },
        "sort_order": 0,
        "is_system_seed": True,
    },
    {
        "content_class": "quick",
        "key": "system.quick.note",
        "name": "快速记录",
        "description": "随手记录的短文",
        "field_schema_json": {},
        "sort_order": 0,
        "is_system_seed": True,
    },
    {
        "content_class": "essay",
        "key": "system.essay.general",
        "name": "通用文章",
        "description": "默认文章类型",
        "field_schema_json": {},
        "sort_order": 0,
        "is_system_seed": True,
    },
    {
        "content_class": "technical",
        "key": "system.technical.tutorial",
        "name": "技术教程",
        "description": "包含代码或操作步骤的技术文章",
        "field_schema_json": {
            "type": "object",
            "properties": {
                "language": {"type": "string", "maxLength": 32},
                "difficulty": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]},
            },
            "additionalProperties": True,
        },
        "sort_order": 0,
        "is_system_seed": True,
    },
]


def seed_content_types(session: Session, user_id: uuid.UUID) -> int:
    """Create system-seed content types for *user_id* if not yet present.

    Idempotent: existing rows with the same ``(user_id, key)`` are skipped.
    Returns the number of rows inserted.
    """
    existing_keys = set(
        session.scalars(
            select(PostContentType.key).where(
                PostContentType.user_id == user_id,
                PostContentType.is_system_seed.is_(True),
            )
        ).all()
    )
    inserted = 0
    for seed in _SEED_TYPES:
        if seed["key"] in existing_keys:
            continue
        session.add(
            PostContentType(
                id=uuid.uuid4(),
                user_id=user_id,
                **seed,
            )
        )
        inserted += 1
    if inserted:
        session.flush()
    return inserted


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def validate_structured_data(
    session: Session,
    user_id: uuid.UUID,
    content_type_id: uuid.UUID,
    structured_data: dict[str, Any],
) -> list[str]:
    """Validate *structured_data* against the content type's field_schema_json.

    Returns a list of warning strings (empty = valid).  Never raises — callers
    decide whether to reject or warn.
    """
    ct = session.scalar(
        select(PostContentType).where(
            PostContentType.id == content_type_id,
            PostContentType.user_id == user_id,
            PostContentType.enabled.is_(True),
        )
    )
    if ct is None:
        return [f"Content type {content_type_id} not found or not enabled"]
    schema = ct.field_schema_json or {}
    if not schema:
        return []
    try:
        jsonschema.validate(structured_data, schema)
        return []
    except jsonschema.ValidationError as exc:
        return [exc.message]
    except jsonschema.SchemaError as exc:
        return [f"Invalid field schema: {exc.message}"]


def list_content_types(
    session: Session, user_id: uuid.UUID, *, content_class: str | None = None
) -> list[PostContentType]:
    q = select(PostContentType).where(
        PostContentType.user_id == user_id,
        PostContentType.enabled.is_(True),
    )
    if content_class:
        q = q.where(PostContentType.content_class == content_class)
    return list(session.scalars(q.order_by(PostContentType.sort_order, PostContentType.name)).all())


def get_content_type(
    session: Session, user_id: uuid.UUID, content_type_id: uuid.UUID
) -> PostContentType | None:
    return session.scalar(
        select(PostContentType).where(
            PostContentType.id == content_type_id,
            PostContentType.user_id == user_id,
        )
    )
