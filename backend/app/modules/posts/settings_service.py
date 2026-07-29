"""Blog settings: safe defaults, section-merge, validation, reference warnings (T021).

BlogSettings is one row per user (primary-key = user_id).  Each of its five
JSON sections has a typed default schema; merging follows a strict policy:
unknown top-level keys are stripped, reference values (content_type_id, skill_id)
that no longer resolve are surfaced as warnings but not removed so the user can
fix them.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import VersionConflictError
from app.models.blog import BlogSettings, BlogSkill, PostContentType

# ---------------------------------------------------------------------------
# Default section schemas
# ---------------------------------------------------------------------------

_SECTION_DEFAULTS: dict[str, Any] = {
    "create_defaults": {
        "content_class": "essay",
        "language": "zh-CN",
        "content_type_id": None,
    },
    "clipboard": {
        "enabled": True,
        "auto_parse": False,
        "default_content_class": "quick",
    },
    "url_capture": {
        "enabled": True,
        "auto_fetch_title": True,
        "auto_extract_body": False,
        "default_content_class": "bookmark",
    },
    "ai_apply": {
        "confirm_before_apply": True,
        "default_fields": ["title", "markdown"],
        "show_diff": True,
    },
    "word_cloud": {
        "enabled": True,
        "min_term_count": 2,
        "max_terms": 100,
        "exclude_terms": [],
    },
}

# Per-section allow-list of top-level keys the client may set.
_SECTION_ALLOWED_KEYS: dict[str, set[str]] = {
    k: set(v.keys()) for k, v in _SECTION_DEFAULTS.items()
}


def _safe_defaults() -> dict[str, Any]:
    return {k: dict(v) for k, v in _SECTION_DEFAULTS.items()}


# ---------------------------------------------------------------------------
# Load / ensure
# ---------------------------------------------------------------------------


def get_settings(session: Session, user_id: uuid.UUID) -> BlogSettings:
    row = session.get(BlogSettings, user_id)
    if row is None:
        row = BlogSettings(
            user_id=user_id,
            schema_version="blog-settings.v1",
            **{f"{k}_json": dict(v) for k, v in _SECTION_DEFAULTS.items()},
        )
        session.add(row)
        session.flush()
    return row


def settings_to_dict(row: BlogSettings) -> dict[str, Any]:
    return {
        "create_defaults": dict(row.create_defaults_json or {}),
        "clipboard": dict(row.clipboard_json or {}),
        "url_capture": dict(row.url_capture_json or {}),
        "ai_apply": dict(row.ai_apply_json or {}),
        "word_cloud": dict(row.word_cloud_json or {}),
        "version": row.version,
        "schema_version": row.schema_version,
    }


# ---------------------------------------------------------------------------
# Merge / update
# ---------------------------------------------------------------------------


def _merge_section(section: str, existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge *patch* into *existing* for *section*, stripping unknown keys."""
    defaults = _SECTION_DEFAULTS[section]
    allowed = _SECTION_ALLOWED_KEYS[section]
    merged = dict(defaults)
    merged.update(existing)
    for k, v in patch.items():
        if k in allowed:
            merged[k] = v
    return {k: merged[k] for k in defaults}  # strip any legacy keys not in defaults


def update_settings(
    session: Session,
    user_id: uuid.UUID,
    patch: dict[str, Any],
    *,
    version: int,
) -> tuple[BlogSettings, list[str]]:
    """Merge *patch* sections into persisted settings.

    Returns ``(updated_row, warnings)`` where warnings list any reference IDs
    that could not be resolved.  Raises VersionConflictError on stale version.
    """
    row = get_settings(session, user_id)
    if row.version != version:
        raise VersionConflictError("Settings modified; refresh", code="version_conflict")

    warnings: list[str] = []
    section_map = {
        "create_defaults": "create_defaults_json",
        "clipboard": "clipboard_json",
        "url_capture": "url_capture_json",
        "ai_apply": "ai_apply_json",
        "word_cloud": "word_cloud_json",
    }
    for section, attr in section_map.items():
        if section not in patch:
            continue
        existing = dict(getattr(row, attr) or {})
        merged = _merge_section(section, existing, patch[section])
        warns = _validate_section_refs(session, user_id, section, merged)
        warnings.extend(warns)
        setattr(row, attr, merged)

    row.version += 1
    return row, warnings


# ---------------------------------------------------------------------------
# Reference validation
# ---------------------------------------------------------------------------


def _validate_section_refs(
    session: Session, user_id: uuid.UUID, section: str, data: dict[str, Any]
) -> list[str]:
    warnings: list[str] = []

    if section == "create_defaults":
        ct_id = data.get("content_type_id")
        if ct_id:
            try:
                uid = uuid.UUID(str(ct_id))
                exists = session.scalar(
                    select(PostContentType.id).where(
                        PostContentType.id == uid,
                        PostContentType.user_id == user_id,
                        PostContentType.enabled.is_(True),
                    )
                )
                if not exists:
                    warnings.append(
                        f"create_defaults.content_type_id {ct_id!r} not found or disabled"
                    )
            except (ValueError, AttributeError):
                warnings.append(f"create_defaults.content_type_id {ct_id!r} is not a valid UUID")

    return warnings


def validate_references(
    session: Session, user_id: uuid.UUID, row: BlogSettings
) -> list[str]:
    """Scan all sections for stale references and return warning strings."""
    warnings: list[str] = []
    section_map = {
        "create_defaults": row.create_defaults_json,
        "clipboard": row.clipboard_json,
        "url_capture": row.url_capture_json,
        "ai_apply": row.ai_apply_json,
        "word_cloud": row.word_cloud_json,
    }
    for section, data in section_map.items():
        warnings.extend(_validate_section_refs(session, user_id, section, data or {}))

    # Validate any skill_id references stored in create_defaults
    skill_id = (row.create_defaults_json or {}).get("default_skill_id")
    if skill_id:
        try:
            uid = uuid.UUID(str(skill_id))
            exists = session.scalar(
                select(BlogSkill.id).where(
                    BlogSkill.id == uid,
                    BlogSkill.user_id == user_id,
                    BlogSkill.enabled.is_(True),
                    BlogSkill.deleted_at.is_(None),
                )
            )
            if not exists:
                warnings.append(
                    f"create_defaults.default_skill_id {skill_id!r} not found, disabled, or deleted"
                )
        except (ValueError, AttributeError):
            warnings.append(
                f"create_defaults.default_skill_id {skill_id!r} is not a valid UUID"
            )
    return warnings
