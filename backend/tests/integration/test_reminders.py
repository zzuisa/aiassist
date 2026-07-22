"""Reminder claiming, unique delivery, critical routing, dispatch audit."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.db.session import session_scope
from app.models.notifications import Notification, NotificationDelivery
from app.models.scheduling import Reminder
from app.models.tasks import Task
from app.modules.notifications import reminder_service
from app.modules.tasks import service as task_service
from app.modules.tasks.schemas import TaskCreate

pytestmark = [pytest.mark.integration]


def _task(session, user_id) -> Task:
    return task_service.create_task(session, user_id, TaskCreate(title="房东", type="task"))


def test_claim_due_reminders_marks_claimed(make_user):
    user = make_user()
    past = datetime.now(UTC) - timedelta(minutes=1)
    with session_scope() as s:
        task = _task(s, user.id)
        reminder_service.create_reminder(
            s, user.id, task.id, channel="in_app", trigger_at=past, is_critical=True
        )
        uid = user.id

    with session_scope() as s:
        due = reminder_service.claim_due_reminders(s, datetime.now(UTC))
        assert len(due) == 1
        assert due[0].status == "claimed"

    with session_scope() as s:
        # A second claim within the stale window returns nothing (already claimed).
        again = reminder_service.claim_due_reminders(s, datetime.now(UTC))
        assert again == []
    _ = uid


def test_dispatch_creates_unique_delivery_and_notification(make_user):
    user = make_user()
    past = datetime.now(UTC) - timedelta(minutes=1)
    with session_scope() as s:
        task = _task(s, user.id)
        reminder_service.create_reminder(
            s, user.id, task.id, channel="in_app", trigger_at=past, is_critical=True
        )
        uid = user.id

    with session_scope() as s:
        due = reminder_service.claim_due_reminders(s, datetime.now(UTC))
        reminder_service.dispatch_reminder(s, due[0])

    with session_scope() as s:
        from sqlalchemy import func, select

        notifs = s.scalar(
            select(func.count()).select_from(Notification).where(Notification.user_id == uid)
        )
        deliveries = s.scalar(
            select(func.count())
            .select_from(NotificationDelivery)
            .where(NotificationDelivery.user_id == uid)
        )
        reminder = s.scalars(select(Reminder).where(Reminder.user_id == uid)).one()
        assert notifs == 1
        assert deliveries == 1
        assert reminder.status == "sent"


def test_critical_reminder_routes_to_critical_queue(make_user):
    user = make_user()
    past = datetime.now(UTC) - timedelta(minutes=1)
    with session_scope() as s:
        task = _task(s, user.id)
        reminder_service.create_reminder(
            s, user.id, task.id, channel="in_app", trigger_at=past, is_critical=True
        )
    with session_scope() as s:
        due = reminder_service.claim_due_reminders(s, datetime.now(UTC))
        reminder_service.dispatch_reminder(s, due[0])

    with session_scope() as s:
        from app.models.foundation import OutboxEvent
        from sqlalchemy import select

        ev = s.scalars(
            select(OutboxEvent).where(OutboxEvent.event_type == "notification.created")
        ).one()
        assert ev.routing_key.startswith("notification.critical")


def test_duplicate_idempotency_key_rejected(make_user):
    user = make_user()
    trigger = datetime.now(UTC) + timedelta(hours=1)
    with session_scope() as s:
        task = _task(s, user.id)
        reminder_service.create_reminder(s, user.id, task.id, channel="in_app", trigger_at=trigger)

    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), session_scope() as s:
        # Same task/channel/trigger -> same idempotency key -> unique violation.
        task_id = s.scalars(__import__("sqlalchemy").select(Task.id)).first()
        reminder_service.create_reminder(s, user.id, task_id, channel="in_app", trigger_at=trigger)


def test_recompute_reminders_on_task_time_change(make_user):
    user = make_user()
    with session_scope() as s:
        task = _task(s, user.id)
        task.due_at = datetime.now(UTC) + timedelta(hours=2)
        reminder_service.create_reminder(
            s,
            user.id,
            task.id,
            channel="in_app",
            trigger_at=task.due_at - timedelta(minutes=30),
            offset_minutes=30,
        )
        tid = task.id

    with session_scope() as s:
        task = s.get(Task, tid)
        task.due_at = datetime.now(UTC) + timedelta(hours=5)
        reminder_service.recompute_task_reminders(s, task)
        reminder = s.scalars(
            __import__("sqlalchemy").select(Reminder).where(Reminder.task_id == tid)
        ).one()
        expected = task.due_at - timedelta(minutes=30)
        assert abs((reminder.trigger_at - expected).total_seconds()) < 1


_ = uuid
