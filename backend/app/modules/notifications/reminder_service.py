"""Due-reminder scanning and delivery creation.

A Beat scan emits a short command; the worker claims due reminders with SKIP
LOCKED and, in one transaction, creates a unique notification + delivery and an
outbox command routed to `critical` (important) or `notification` (normal).
Reminders are recomputed when the task time changes; already-sent ones persist.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notifications import Notification, NotificationDelivery
from app.models.scheduling import Reminder
from app.models.tasks import Task
from app.services.outbox.publisher import append_event

CLAIM_STALE_MINUTES = 5


def create_reminder(
    session: Session,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    channel: str,
    trigger_at: datetime,
    offset_minutes: int | None = None,
    is_critical: bool = False,
) -> Reminder:
    key = f"reminder:{task_id}:{channel}:{int(trigger_at.timestamp())}"
    reminder = Reminder(
        id=uuid.uuid4(),
        user_id=user_id,
        task_id=task_id,
        channel=channel,
        trigger_at=trigger_at,
        offset_minutes=offset_minutes,
        is_critical=is_critical,
        idempotency_key=key,
    )
    session.add(reminder)
    return reminder


def claim_due_reminders(
    session: Session, now: datetime | None = None, limit: int = 50
) -> list[Reminder]:
    now = now or datetime.now(UTC)
    stale = now - timedelta(minutes=CLAIM_STALE_MINUTES)
    rows = (
        session.execute(
            select(Reminder)
            .where(
                Reminder.trigger_at <= now,
                Reminder.status.in_(["scheduled", "claimed"]),
                (
                    (Reminder.status == "scheduled")
                    | ((Reminder.status == "claimed") & (Reminder.claimed_at < stale))
                ),
            )
            .order_by(Reminder.trigger_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    for r in rows:
        r.status = "claimed"
        r.claimed_at = now
    session.flush()
    return list(rows)


def dispatch_reminder(session: Session, reminder: Reminder) -> Notification:
    """Create the in-app notification + delivery and route an outbox command."""
    task = session.get(Task, reminder.task_id)
    title = task.title if task else "提醒"
    notification = Notification(
        id=uuid.uuid4(),
        user_id=reminder.user_id,
        type="task_due",
        title=title,
        body="任务即将到期" if reminder.channel == "in_app" else "邮件提醒",
        entity_type="task",
        entity_id=reminder.task_id,
        status="unread",
    )
    session.add(notification)
    session.flush()

    session.add(
        NotificationDelivery(
            id=uuid.uuid4(),
            user_id=reminder.user_id,
            notification_id=notification.id,
            reminder_id=reminder.id,
            channel=reminder.channel,
            status="pending",
            attempt_no=1,
        )
    )

    routing = "notification.critical" if reminder.is_critical else "notification.in_app"
    if reminder.channel == "email":
        routing = "notification.email" if not reminder.is_critical else "notification.critical"
    append_event(
        session,
        event_type="notification.created",
        aggregate_type="notification",
        aggregate_id=notification.id,
        routing_key=f"{routing}.send",
        payload={
            "notification_id": str(notification.id),
            "reminder_id": str(reminder.id),
            "channel": reminder.channel,
            "critical": reminder.is_critical,
        },
        user_id=reminder.user_id,
    )
    reminder.status = "sent"
    reminder.sent_at = datetime.now(UTC)
    return notification


def recompute_task_reminders(session: Session, task: Task) -> None:
    """Reschedule not-yet-sent reminders when the task's time changes."""
    reminders = session.scalars(
        select(Reminder).where(
            Reminder.task_id == task.id, Reminder.status.in_(["scheduled", "claimed"])
        )
    ).all()
    for r in reminders:
        if r.offset_minutes is not None and task.due_at is not None:
            r.trigger_at = task.due_at - timedelta(minutes=r.offset_minutes)
            r.status = "scheduled"
            r.claimed_at = None


# --- Dedicated "important" reminder: email 4 hours before the event start -----
IMPORTANT_PURPOSE = "important_start_4h"
IMPORTANT_OFFSET_MIN = 240


def _important_idem_key(user_id: uuid.UUID, task_id: uuid.UUID) -> str:
    # Stable per user/task/purpose — NOT based on the movable trigger time — so
    # repeated toggles/reschedules never create a second row or a duplicate email.
    return f"important4h:{user_id}:{task_id}"


def _find_important(session: Session, task_id: uuid.UUID) -> Reminder | None:
    return session.scalar(
        select(Reminder).where(
            Reminder.task_id == task_id,
            Reminder.purpose == IMPORTANT_PURPOSE,
            Reminder.channel == "email",
        )
    )


def sync_important_reminder(session: Session, task: Task, now: datetime | None = None) -> None:
    """Create / reschedule / cancel the dedicated 4h-before-start email reminder so
    it always matches the task's importance and start time.

    Rules (FR-006..FR-008): important + future start -> one email at start-4h; if
    start is <4h away, send ASAP; started/no-start -> no history backfill; removing
    importance cancels an unsent reminder; an already-sent reminder is never resent.
    """
    now = now or datetime.now(UTC)
    existing = _find_important(session, task.id)
    important = bool(task.importance and task.importance > 0)

    # Not important (or start removed): cancel anything not yet sent.
    if not important or task.start_at is None:
        if existing is not None and existing.status in ("scheduled", "claimed"):
            existing.status = "cancelled"
            existing.claimed_at = None
        return

    # A reminder already sent must never be resent, regardless of toggles.
    if existing is not None and existing.status == "sent":
        return

    # Event already started: do not backfill a historical reminder.
    if task.start_at <= now:
        if existing is not None and existing.status in ("scheduled", "claimed"):
            existing.status = "cancelled"
            existing.claimed_at = None
        return

    ideal = task.start_at - timedelta(minutes=IMPORTANT_OFFSET_MIN)
    trigger_at = ideal if ideal > now else now  # <4h to start -> send ASAP

    if existing is None:
        session.add(
            Reminder(
                id=uuid.uuid4(),
                user_id=task.user_id,
                task_id=task.id,
                channel="email",
                purpose=IMPORTANT_PURPOSE,
                anchor="start_at",
                trigger_at=trigger_at,
                offset_minutes=IMPORTANT_OFFSET_MIN,
                is_critical=True,
                status="scheduled",
                idempotency_key=_important_idem_key(task.user_id, task.id),
            )
        )
    else:
        existing.trigger_at = trigger_at
        existing.status = "scheduled"
        existing.claimed_at = None


def important_reminder_summary(session: Session, task: Task) -> dict | None:
    """User-facing status of the dedicated reminder, derived from its delivery state.

    States: scheduled, sending, sent, failed, unconfigured, missing_start,
    not_applicable. Returns None when the task is not important.
    """
    if not (task.importance and task.importance > 0):
        return None
    if task.start_at is None:
        return {"state": "missing_start", "trigger_at": None}
    reminder = _find_important(session, task.id)
    if reminder is None:
        return {"state": "not_applicable", "trigger_at": None}
    trigger_iso = reminder.trigger_at.isoformat() if reminder.trigger_at else None
    if reminder.status == "cancelled":
        return {"state": "not_applicable", "trigger_at": trigger_iso}
    if reminder.status == "failed":
        state = "unconfigured" if (reminder.last_error or "") == "smtp_unconfigured" else "failed"
        return {"state": state, "trigger_at": trigger_iso}
    if reminder.status in ("scheduled", "claimed"):
        state = "scheduled" if reminder.status == "scheduled" else "sending"
        return {"state": state, "trigger_at": trigger_iso}
    # Dispatched: report the ACTUAL email delivery state, not "dispatched == sent".
    delivery = session.scalar(
        select(NotificationDelivery)
        .where(
            NotificationDelivery.reminder_id == reminder.id,
            NotificationDelivery.channel == "email",
        )
        .order_by(NotificationDelivery.id.desc())
    )
    if delivery is None:
        return {"state": "sending", "trigger_at": trigger_iso}
    if delivery.status == "sent":
        return {"state": "sent", "trigger_at": trigger_iso}
    if delivery.status == "failed":
        state = "unconfigured" if (delivery.last_error or "") == "smtp_unconfigured" else "failed"
        return {"state": state, "trigger_at": trigger_iso}
    return {"state": "sending", "trigger_at": trigger_iso}  # pending / sending
