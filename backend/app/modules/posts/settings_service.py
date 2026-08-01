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

from app.core.errors import ValidationError, VersionConflictError
from app.models.blog import BlogSettings, BlogSkill, PostContentType
from app.models.foundation import ActivityLog, Category, Tag

# ---------------------------------------------------------------------------
# Default section schemas
# ---------------------------------------------------------------------------

_SECTION_DEFAULTS: dict[str, Any] = {
    "create_defaults": {
        "content_class": "essay",
        "language": "zh-CN",
        "content_type_id": None,
        "category_id": None,
        "tag_ids": [],
        "status": "draft",
        "editor_mode": "rich",
        "ai_enabled": False,
        "default_skill_id": None,
        "model": None,
        "generate_summary": True,
        "generate_keywords": True,
        "recommend_tags": True,
        "retain_original": True,
    },
    "clipboard": {
        "enabled": True,
        "auto_parse": False,
        "default_content_class": "quick",
        "cleanup_format": True,
        "retain_original": True,
        "detect_urls": True,
        "auto_ai": False,
        "default_skill_id": None,
    },
    "url_capture": {
        "enabled": True,
        "auto_fetch_title": True,
        "auto_extract_body": False,
        "default_content_class": "bookmark",
        "retain_original": True,
        "retain_snapshot": False,
        "extract_images": False,
        "auto_ai": False,
        "default_skill_id": None,
    },
    "ai_apply": {
        "confirm_before_apply": True,
        "default_fields": ["title", "markdown"],
        "show_diff": True,
        "default_provider": "radio",
        "allow_auto_apply": False,
        "auto_apply_fields": [],
        "confirm_fields": ["markdown", "content_class", "language", "structured_data"],
        "merge_on_version_change": True,
        "retain_job_history": True,
    },
    "word_cloud": {
        "enabled": True,
        "min_term_count": 2,
        "max_terms": 100,
        "exclude_terms": [],
        "excluded_content_classes": [],
    },
}

_AI_FIELDS = {
    "title",
    "subtitle",
    "summary",
    "markdown",
    "content_class",
    "language",
    "structured_data",
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
        "create_defaults": _merge_section(
            "create_defaults", dict(row.create_defaults_json or {}), {}
        ),
        "clipboard": _merge_section("clipboard", dict(row.clipboard_json or {}), {}),
        "url_capture": _merge_section("url_capture", dict(row.url_capture_json or {}), {}),
        "ai_apply": _merge_section("ai_apply", dict(row.ai_apply_json or {}), {}),
        "word_cloud": _merge_section("word_cloud", dict(row.word_cloud_json or {}), {}),
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


def get_default_ai_provider(session: Session, user_id: uuid.UUID) -> str:
    row = get_settings(session, user_id)
    provider = (row.ai_apply_json or {}).get("default_provider", "radio")
    return provider if provider in {"radio", "aiassist"} else "radio"


def set_default_ai_provider(
    session: Session, user_id: uuid.UUID, provider_key: str
) -> BlogSettings:
    if provider_key not in {"radio", "aiassist"}:
        raise ValueError("unsupported AI optimization provider")
    row = get_settings(session, user_id)
    row.ai_apply_json = _merge_section(
        "ai_apply",
        dict(row.ai_apply_json or {}),
        {"default_provider": provider_key},
    )
    row.version += 1
    return row


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
    changed_sections: list[str] = []
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
        _validate_section_values(section, merged)
        warns = _validate_section_refs(session, user_id, section, merged)
        warnings.extend(warns)
        setattr(row, attr, merged)
        if merged != _merge_section(section, existing, {}):
            changed_sections.append(section)

    row.version += 1
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="blog.settings.updated",
            entity_type="blog_settings",
            entity_id=user_id,
            before_summary_json={"version": version},
            after_summary_json={
                "version": row.version,
                "changed_sections": changed_sections,
                "auto_apply_enabled": bool(settings_to_dict(row)["ai_apply"]["allow_auto_apply"]),
            },
        )
    )
    return row, warnings


def section_defaults(section: str) -> dict[str, Any]:
    if section not in _SECTION_DEFAULTS:
        raise ValidationError("unknown settings section", code="invalid_settings_section")
    return dict(_SECTION_DEFAULTS[section])


def _validate_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValidationError(f"{field} must be a string list", code="invalid_blog_settings")
    return value


def _validate_section_values(section: str, data: dict[str, Any]) -> None:
    if section == "ai_apply":
        automatic = set(_validate_string_list(data["auto_apply_fields"], "auto_apply_fields"))
        confirmed = set(_validate_string_list(data["confirm_fields"], "confirm_fields"))
        if not automatic <= _AI_FIELDS or not confirmed <= _AI_FIELDS:
            raise ValidationError("unknown AI result field", code="invalid_blog_settings")
        if automatic & confirmed or "markdown" in automatic:
            raise ValidationError(
                "automatic and confirmation fields conflict", code="settings_policy_conflict"
            )
        if not data["allow_auto_apply"] and automatic:
            raise ValidationError(
                "automatic fields require auto apply", code="settings_policy_conflict"
            )
        if data["default_provider"] not in {"radio", "aiassist"}:
            raise ValidationError("invalid AI provider", code="invalid_blog_settings")
    elif section == "word_cloud":
        try:
            minimum = int(data["min_term_count"])
            maximum = int(data["max_terms"])
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "word-cloud limits must be integers", code="invalid_blog_settings"
            ) from exc
        if not 1 <= minimum <= 100_000:
            raise ValidationError("invalid minimum term count", code="invalid_blog_settings")
        if not 1 <= maximum <= 500:
            raise ValidationError("invalid maximum terms", code="invalid_blog_settings")
        _validate_string_list(data["exclude_terms"], "exclude_terms")
        _validate_string_list(data["excluded_content_classes"], "excluded_content_classes")
    elif section == "create_defaults":
        _validate_string_list(data["tag_ids"], "tag_ids")


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

        category_id = data.get("category_id")
        if category_id and not _owned_reference_exists(
            session, Category, user_id, category_id, enabled=True
        ):
            warnings.append(f"create_defaults.category_id {category_id!r} not found or disabled")
        for tag_id in data.get("tag_ids", []):
            if not _owned_reference_exists(session, Tag, user_id, tag_id):
                warnings.append(f"create_defaults.tag_id {tag_id!r} not found")

    if section in {"create_defaults", "clipboard", "url_capture"}:
        skill_id = data.get("default_skill_id")
        if skill_id and not _owned_reference_exists(
            session, BlogSkill, user_id, skill_id, enabled=True, deleted=True
        ):
            warnings.append(f"{section}.default_skill_id {skill_id!r} not found or disabled")

    return warnings


def _owned_reference_exists(
    session: Session,
    model: Any,
    user_id: uuid.UUID,
    raw_id: Any,
    *,
    enabled: bool = False,
    deleted: bool = False,
) -> bool:
    try:
        entity_id = uuid.UUID(str(raw_id))
    except (TypeError, ValueError, AttributeError):
        return False
    query = select(model.id).where(model.id == entity_id, model.user_id == user_id)
    if enabled:
        query = query.where(model.enabled.is_(True))
    if deleted:
        query = query.where(model.deleted_at.is_(None))
    return session.scalar(query) is not None


def validate_references(session: Session, user_id: uuid.UUID, row: BlogSettings) -> list[str]:
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
    return warnings
