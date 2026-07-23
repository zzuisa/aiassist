"""User settings service: account, timezone, notification prefs, password change."""

from __future__ import annotations

import uuid
from zoneinfo import ZoneInfo, available_timezones

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthenticationError, NotFoundError, ValidationError
from app.models.foundation import ActivityLog, User
from app.modules.auth import service as auth_service

_VALID_TZ = available_timezones()


def get_user(session: Session, user_id: uuid.UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return user


def dependency_states() -> dict:
    s = get_settings()
    return {
        "mail": {"configured": bool(s.smtp_host), "state": s.mail_status(), "provider_key": None},
        "llm": {
            "configured": s.llm_provider != "none",
            "state": s.llm_status(),
            "provider_key": s.llm_provider if s.llm_provider != "none" else None,
        },
        "speech": {
            "configured": s.speech_provider != "none",
            "state": s.speech_status(),
            "provider_key": s.speech_provider if s.speech_provider != "none" else None,
        },
        "storage": {
            "configured": True,
            "state": s.storage_status(),
            "provider_key": s.storage_provider,
        },
    }


def update_settings(session: Session, user_id: uuid.UUID, data: dict) -> User:
    user = get_user(session, user_id)
    if "display_name" in data:
        user.display_name = data["display_name"]
    if "timezone" in data:
        tz = data["timezone"]
        if tz not in _VALID_TZ:
            raise ValidationError("Unknown timezone", code="invalid_timezone")
        # Validate constructibility as a defensive double-check.
        ZoneInfo(tz)
        user.timezone = tz
    if "locale" in data:
        user.locale = data["locale"]
    if "notification_preferences" in data and data["notification_preferences"] is not None:
        prefs = data["notification_preferences"]
        # Email cannot be enabled when SMTP is unconfigured.
        if prefs.get("email_enabled") and not get_settings().smtp_host:
            prefs = {**prefs, "email_enabled": False}
        user.notification_preferences = prefs
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="settings.updated",
            entity_type="user",
            entity_id=user_id,
        )
    )
    return user


def change_password(
    session: Session, user_id: uuid.UUID, current_password: str, new_password: str
) -> None:
    user = get_user(session, user_id)
    if not auth_service.verify_password(user.password_hash, current_password):
        raise AuthenticationError("Current password is incorrect", code="invalid_credentials")
    if len(new_password) < 12:
        raise ValidationError("Password too short", code="weak_password")
    user.password_hash = auth_service.hash_password(new_password)
    # Revoke all other sessions after a password change.
    auth_service.revoke_all_sessions(session, user_id)
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="settings.password_changed",
            entity_type="user",
            entity_id=user_id,
        )
    )
