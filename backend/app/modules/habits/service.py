"""Habit service: CRUD, idempotent task generation, check-in/skip, statistics."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.foundation import User
from app.models.habits import Habit, HabitLog
from app.models.tasks import Task
from app.modules.habits.recurrence import is_valid_rule, occurs_on
from app.services.outbox.publisher import append_event


def create_habit(session: Session, user_id: uuid.UUID, data: dict) -> Habit:
    rule = data["recurrence_rule"]
    if not is_valid_rule(rule):
        raise ValidationError("Unsupported recurrence rule", code="invalid_recurrence")
    habit = Habit(
        id=uuid.uuid4(),
        user_id=user_id,
        name=data["name"],
        description=data.get("description"),
        recurrence_rule=rule,
        suggested_time_local=data.get("suggested_time_local"),
        target_minutes=data.get("target_minutes"),
        minimum_amount=data.get("minimum_amount"),
        unit=data.get("unit"),
        priority=data.get("priority", 0),
        auto_create_task=data.get("auto_create_task", True),
        is_ai_adjustable=data.get("is_ai_adjustable", True),
        status="active",
    )
    session.add(habit)
    session.flush()
    return habit


def get_habit(session: Session, user_id: uuid.UUID, habit_id: uuid.UUID) -> Habit:
    habit = session.get(Habit, habit_id)
    if habit is None or habit.user_id != user_id or habit.deleted_at is not None:
        raise NotFoundError("Habit not found")
    return habit


def list_habits(session: Session, user_id: uuid.UUID) -> list[Habit]:
    return list(
        session.scalars(
            select(Habit).where(
                Habit.user_id == user_id,
                Habit.deleted_at.is_(None),
                Habit.status != "archived",
            )
        ).all()
    )


def archive_habit(session: Session, user_id: uuid.UUID, habit_id: uuid.UUID) -> None:
    habit = get_habit(session, user_id, habit_id)
    habit.status = "archived"
    habit.deleted_at = datetime.now(UTC)


def generate_habit_task(session: Session, habit: Habit, local_date: date) -> Task | None:
    """Idempotently create today's habit task. Returns the task or None if it
    already exists / the habit does not occur / auto-create is off."""
    if not habit.auto_create_task or habit.status != "active":
        return None
    if not occurs_on(habit.recurrence_rule, local_date):
        return None
    # Fast path: existing task for this (habit, date).
    existing = session.scalar(
        select(Task).where(
            Task.user_id == habit.user_id,
            Task.habit_id == habit.id,
            Task.habit_date == local_date,
        )
    )
    if existing is not None:
        return existing

    task = Task(
        id=uuid.uuid4(),
        user_id=habit.user_id,
        type="habit_task",
        title=habit.name,
        status="todo",
        priority=habit.priority,
        habit_id=habit.id,
        habit_date=local_date,
        source_type="habit",
        source_id=habit.id,
    )
    session.add(task)
    try:
        session.flush()
    except IntegrityError:
        # Concurrent generation: the unique (user, habit, date) constraint won.
        session.rollback()
        return session.scalar(
            select(Task).where(
                Task.user_id == habit.user_id,
                Task.habit_id == habit.id,
                Task.habit_date == local_date,
            )
        )
    append_event(
        session,
        event_type="habit.task_generated",
        aggregate_type="task",
        aggregate_id=task.id,
        routing_key="search.index.task.created",
        payload={"task_id": str(task.id), "habit_id": str(habit.id)},
        user_id=habit.user_id,
    )
    return task


def generate_for_user(session: Session, user: User, local_date: date | None = None) -> int:
    """Generate today's habit tasks for a user; returns count generated."""
    tz = ZoneInfo(user.timezone)
    today = local_date or datetime.now(UTC).astimezone(tz).date()
    count = 0
    habits = session.scalars(
        select(Habit).where(
            Habit.user_id == user.id, Habit.status == "active", Habit.deleted_at.is_(None)
        )
    ).all()
    for habit in habits:
        task = generate_habit_task(session, habit, today)
        if task is not None:
            count += 1
    return count


def _upsert_log(session: Session, habit: Habit, local_date: date, **fields: object) -> HabitLog:
    log = session.scalar(
        select(HabitLog).where(
            HabitLog.user_id == habit.user_id,
            HabitLog.habit_id == habit.id,
            HabitLog.local_date == local_date,
        )
    )
    if log is None:
        log = HabitLog(
            id=uuid.uuid4(),
            user_id=habit.user_id,
            habit_id=habit.id,
            local_date=local_date,
            status=fields.get("status", "completed"),
        )
        session.add(log)
    for k, v in fields.items():
        setattr(log, k, v)
    session.flush()
    return log


def check_in(
    session: Session,
    user_id: uuid.UUID,
    habit_id: uuid.UUID,
    local_date: date,
    *,
    status: str,
    amount: float | None = None,
    duration_seconds: int | None = None,
) -> HabitLog:
    habit = get_habit(session, user_id, habit_id)
    log = _upsert_log(
        session,
        habit,
        local_date,
        status=status,
        amount=amount,
        duration_seconds=duration_seconds,
        skip_reason=None,
        skip_note=None,
        completed_at=datetime.now(UTC),
    )
    # Sync the generated task to completed if present.
    task = session.scalar(
        select(Task).where(
            Task.user_id == user_id, Task.habit_id == habit_id, Task.habit_date == local_date
        )
    )
    if task is not None and status == "completed":
        task.status = "completed"
        task.completed_at = datetime.now(UTC)
        task.version += 1
    append_event(
        session,
        event_type="habit.checked_in",
        aggregate_type="habit",
        aggregate_id=habit_id,
        routing_key="search.index.habit.updated",
        payload={"habit_id": str(habit_id)},
        user_id=user_id,
    )
    return log


def skip(
    session: Session,
    user_id: uuid.UUID,
    habit_id: uuid.UUID,
    local_date: date,
    *,
    reason: str,
    note: str | None = None,
) -> HabitLog:
    habit = get_habit(session, user_id, habit_id)
    return _upsert_log(
        session,
        habit,
        local_date,
        status="skipped",
        skip_reason=reason,
        skip_note=note,
        amount=None,
        duration_seconds=None,
        completed_at=None,
    )


def compute_stats(session: Session, user_id: uuid.UUID, from_date: date, to_date: date) -> dict:
    """Streak (consecutive completed days up to to_date), completion rate, heatmap.

    Only `completed` counts toward streak by default; `skipped`/`partial` do not.
    """
    logs = session.scalars(
        select(HabitLog).where(
            HabitLog.user_id == user_id,
            HabitLog.local_date >= from_date,
            HabitLog.local_date <= to_date,
        )
    ).all()
    by_date: dict[str, dict[str, int]] = {}
    completed_days: set[date] = set()
    total = 0
    completed = 0
    for log in logs:
        d = log.local_date.isoformat()
        bucket = by_date.setdefault(d, {"completed": 0, "partial": 0, "skipped": 0})
        bucket[log.status] = bucket.get(log.status, 0) + 1
        total += 1
        if log.status == "completed":
            completed += 1
            completed_days.add(log.local_date)

    # Current streak: count back from to_date while each day has a completion.
    streak = 0
    cursor = to_date
    while cursor in completed_days:
        streak += 1
        cursor = cursor - timedelta(days=1)

    rate = round(completed / total, 3) if total else 0.0
    return {
        "streak": streak,
        "completion_rate": rate,
        "total_logs": total,
        "completed_logs": completed,
        "heatmap": by_date,
    }
