"""Habit recurrence, idempotent generation, check-in/skip, streak stats."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from app.db.session import session_scope
from app.modules.habits import service
from app.modules.habits.recurrence import is_valid_rule, occurs_on

pytestmark = [pytest.mark.integration]


def test_recurrence_daily_and_weekly():
    assert occurs_on("FREQ=DAILY", date(2026, 7, 27))
    # 2026-07-27 is a Monday.
    assert occurs_on("FREQ=WEEKLY;BYDAY=MO", date(2026, 7, 27))
    assert not occurs_on("FREQ=WEEKLY;BYDAY=TU", date(2026, 7, 27))
    assert is_valid_rule("FREQ=MONTHLY;BYMONTHDAY=1,15")
    assert not is_valid_rule("FREQ=YEARLY")


def _make_habit(session, user_id, rule="FREQ=DAILY", **kw):
    return service.create_habit(session, user_id, {"name": "喝水", "recurrence_rule": rule, **kw})


def test_generation_is_idempotent(make_user):
    from app.models.habits import Habit

    user = make_user()
    today = date(2026, 7, 27)
    with session_scope() as s:
        habit = _make_habit(s, user.id)
        hid = habit.id
        uid = user.id

    # Generate twice for the same day (simulates duplicate Beat/worker runs).
    for _ in range(2):
        with session_scope() as s:
            service.generate_habit_task(s, s.get(Habit, hid), today)

    with session_scope() as s:
        from app.models.tasks import Task
        from sqlalchemy import func, select

        count = s.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.user_id == uid, Task.habit_id == hid, Task.habit_date == today)
        )
        assert count == 1


def test_check_in_and_skip_and_stats(make_user):
    user = make_user()
    d1 = date(2026, 7, 27)
    d2 = date(2026, 7, 28)
    with session_scope() as s:
        habit = _make_habit(s, user.id)
        hid = habit.id
        uid = user.id

    with session_scope() as s:
        service.check_in(s, uid, hid, d1, status="completed", amount=1)
    with session_scope() as s:
        service.skip(s, uid, hid, d2, reason="too_tired", note="累")

    with session_scope() as s:
        stats = service.compute_stats(s, uid, d1, d2)
        # One completed, one skipped: rate 0.5, skip does not extend streak.
        assert stats["completed_logs"] == 1
        assert stats["total_logs"] == 2
        assert stats["completion_rate"] == 0.5
        # Streak measured back from d2 (skipped) is 0.
        assert stats["streak"] == 0


def test_streak_counts_consecutive_completed(make_user):
    user = make_user()
    days = [date(2026, 7, 25), date(2026, 7, 26), date(2026, 7, 27)]
    with session_scope() as s:
        habit = _make_habit(s, user.id)
        hid = habit.id
        uid = user.id
    for d in days:
        with session_scope() as s:
            service.check_in(s, uid, hid, d, status="completed")
    with session_scope() as s:
        stats = service.compute_stats(s, uid, days[0], days[-1])
        assert stats["streak"] == 3


def test_check_in_completes_generated_task(make_user):
    user = make_user()
    today = date(2026, 7, 27)
    with session_scope() as s:
        habit = _make_habit(s, user.id)
        hid = habit.id
        uid = user.id
    with session_scope() as s:
        from app.models.habits import Habit

        service.generate_habit_task(s, s.get(Habit, hid), today)
    with session_scope() as s:
        service.check_in(s, uid, hid, today, status="completed")
    with session_scope() as s:
        from app.models.tasks import Task
        from sqlalchemy import select

        task = s.scalars(select(Task).where(Task.habit_id == hid, Task.habit_date == today)).one()
        assert task.status == "completed"


_ = timedelta
