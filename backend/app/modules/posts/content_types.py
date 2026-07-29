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

from app.core.errors import NotFoundError, ValidationError
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


def list_all_content_types(session: Session, user_id: uuid.UUID) -> list[PostContentType]:
    """List owned content types (enabled and disabled), for management UIs."""
    return list(
        session.scalars(
            select(PostContentType)
            .where(PostContentType.user_id == user_id)
            .order_by(PostContentType.sort_order, PostContentType.name)
        ).all()
    )


def _validate_field_schema(field_schema: dict[str, Any]) -> None:
    """Reject a field_schema that is not itself a valid JSON Schema."""
    if not field_schema:
        return
    try:
        jsonschema.Draft202012Validator.check_schema(field_schema)
    except jsonschema.SchemaError as exc:
        raise ValidationError(f"Invalid field_schema: {exc.message}", code="invalid_field_schema") from exc


def create_content_type(
    session: Session,
    user_id: uuid.UUID,
    *,
    content_class: str,
    key: str,
    name: str,
    field_schema: dict[str, Any],
    description: str | None = None,
    sort_order: int = 0,
    enabled: bool = True,
) -> PostContentType:
    validate_content_class(content_class)
    _validate_field_schema(field_schema)
    existing = session.scalar(
        select(PostContentType).where(
            PostContentType.user_id == user_id, PostContentType.key == key
        )
    )
    if existing is not None:
        raise ValidationError(f"content type key '{key}' already exists", code="duplicate_key")
    ct = PostContentType(
        id=uuid.uuid4(),
        user_id=user_id,
        content_class=content_class,
        key=key,
        name=name,
        description=description,
        field_schema_json=field_schema,
        schema_version=1,
        sort_order=sort_order,
        enabled=enabled,
    )
    session.add(ct)
    session.flush()
    return ct


def update_content_type(
    session: Session,
    user_id: uuid.UUID,
    content_type_id: uuid.UUID,
    *,
    name: str | None = None,
    description: str | None = None,
    field_schema: dict[str, Any] | None = None,
    sort_order: int | None = None,
    enabled: bool | None = None,
) -> tuple[PostContentType, list[str]]:
    """Update a content type; bump schema_version when the field_schema changes.

    Returns ``(content_type, warnings)``.  A schema change warns because existing
    posts keep their stored structured_data (never rewritten) and may no longer
    validate against the new schema.
    """
    ct = get_content_type(session, user_id, content_type_id)
    if ct is None:
        raise NotFoundError("Content type not found")
    warnings: list[str] = []
    if name is not None:
        ct.name = name
    if description is not None:
        ct.description = description
    if sort_order is not None:
        ct.sort_order = sort_order
    if enabled is not None:
        ct.enabled = enabled
    if field_schema is not None and field_schema != (ct.field_schema_json or {}):
        _validate_field_schema(field_schema)
        ct.field_schema_json = field_schema
        ct.schema_version += 1
        warnings.append(
            "field_schema changed; existing posts keep their stored data and may "
            "need review against schema version "
            f"{ct.schema_version}"
        )
    session.flush()
    return ct, warnings
