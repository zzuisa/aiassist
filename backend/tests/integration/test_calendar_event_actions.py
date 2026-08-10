"""US1: reversible completion, completed-in-calendar, important 4h reminder lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.db.session import session_scope
from app.models.scheduling import Reminder
from app.models.tasks import Task
from app.modules.notifications import reminder_service
from app.modules.tasks import calendar_service
from app.modules.tasks import service as task_service
from app.modules.tasks.schemas import TaskPatch
from sqlalchemy import select

pytestmark = [pytest.mark.integration]


def _make_task(s, user_id, *, start_at=None, importance=0, status="todo") -> Task:
    task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        type="task",
        title="事件",
        status=status,
        priority=0,
        importance=importance,
        start_at=start_at,
        version=1,
    )
    s.add(task)
    s.flush()
    return task


def _important(s, task_id):
    return s.scalar(
        select(Reminder).where(
            Reminder.task_id == task_id, Reminder.purpose == "important_start_4h"
        )
    )


def test_mark_important_schedules_reminder_four_hours_before_start(make_user):
    user = make_user()
    start = datetime.now(UTC) + timedelta(days=1)
    with session_scope() as s:
        task = _make_task(s, user.id, start_at=start)
        task_service.update_task(
            s, user.id, task.id, TaskPatch(version=1, importance=4), {"importance"}
        )
    with session_scope() as s:
        r = _important(s, task.id)
        assert r is not None and r.status == "scheduled"
        assert r.channel == "email" and r.is_critical is True
        assert abs((r.trigger_at - (start - timedelta(minutes=240))).total_seconds()) < 2


def test_remove_important_cancels_unsent_reminder(make_user):
    user = make_user()
    start = datetime.now(UTC) + timedelta(days=1)
    with session_scope() as s:
        task = _make_task(s, user.id, start_at=start)
        task_service.update_task(
            s, user.id, task.id, TaskPatch(version=1, importance=4), {"importance"}
        )
    with session_scope() as s:
        task = task_service.get_task(s, user.id, task.id)
        task_service.update_task(
            s, user.id, task.id, TaskPatch(version=task.version, importance=0), {"importance"}
        )
    with session_scope() as s:
        assert _important(s, task.id).status == "cancelled"


def test_reschedule_recomputes_reminder_and_no_duplicate(make_user):
    user = make_user()
    start = datetime.now(UTC) + timedelta(days=2)
    with session_scope() as s:
        task = _make_task(s, user.id, start_at=start)
        task_service.update_task(
            s, user.id, task.id, TaskPatch(version=1, importance=4), {"importance"}
        )
    new_start = start + timedelta(hours=3)
    with session_scope() as s:
        task = task_service.get_task(s, user.id, task.id)
        calendar_service.reschedule_task(
            s, user.id, task, version=task.version, start_at=new_start, due_at=None
        )
    with session_scope() as s:
        rows = s.scalars(
            select(Reminder).where(
                Reminder.task_id == task.id, Reminder.purpose == "important_start_4h"
            )
        ).all()
        assert len(rows) == 1  # never duplicated
        assert abs((rows[0].trigger_at - (new_start - timedelta(minutes=240))).total_seconds()) < 2


def test_important_within_four_hours_sends_asap(make_user):
    user = make_user()
    start = datetime.now(UTC) + timedelta(hours=1)  # <4h away
    with session_scope() as s:
        task = _make_task(s, user.id, start_at=start)
        task_service.update_task(
            s, user.id, task.id, TaskPatch(version=1, importance=4), {"importance"}
        )
    with session_scope() as s:
        r = _important(s, task.id)
        assert r.status == "scheduled"
        # trigger clamped to ~now (cannot be 4h before a start that is 1h away)
        assert r.trigger_at <= datetime.now(UTC) + timedelta(seconds=2)


def test_missing_start_yields_missing_start_summary(make_user):
    user = make_user()
    with session_scope() as s:
        task = _make_task(s, user.id, start_at=None)
        task_service.update_task(
            s, user.id, task.id, TaskPatch(version=1, importance=4), {"importance"}
        )
        summary = reminder_service.important_reminder_summary(s, task)
        assert summary["state"] == "missing_start"
        assert _important(s, task.id) is None  # nothing scheduled without a start


def test_completion_is_reversible(make_user):
    user = make_user()
    with session_scope() as s:
        task = _make_task(s, user.id, status="todo")
        task_service.complete_task(s, user.id, task.id, task.version, None)
    with session_scope() as s:
        task = task_service.get_task(s, user.id, task.id)
        assert task.status == "completed" and task.completed_at is not None
        task_service.update_task(
            s, user.id, task.id, TaskPatch(version=task.version, status="todo"), {"status"}
        )
    with session_scope() as s:
        task = task_service.get_task(s, user.id, task.id)
        assert task.status == "todo" and task.completed_at is None


def test_completed_event_stays_on_calendar(make_user):
    user = make_user()
    start = datetime.now(UTC) + timedelta(hours=2)
    with session_scope() as s:
        task = _make_task(s, user.id, start_at=start, status="completed")
        week_start = start - timedelta(days=1)
        events, _unscheduled, _ = calendar_service.get_week(s, user.id, week_start)
        assert any(e.id == task.id for e in events)
