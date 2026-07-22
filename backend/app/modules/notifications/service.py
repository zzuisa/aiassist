"""Notification read model: list and mark-read (US2/US6)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notifications import Notification


def list_notifications(
    session: Session, user_id: uuid.UUID, limit: int = 100
) -> list[Notification]:
    return list(
        session.scalars(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        ).all()
    )


def mark_read(session: Session, user_id: uuid.UUID, notification_id: uuid.UUID) -> None:
    notification = session.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        return  # idempotent, no info leak
    if notification.status == "unread":
        notification.status = "read"
        notification.read_at = datetime.now(UTC)
