"""Week calendar queries, interval conflict detection, fixed-event rules, undo.

Pure interval logic is separated so it is unit-testable without a database.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models.foundation import ActivityLog
from app.models.tasks import Task
from app.modules.tasks.service import _check_version, _emit


@dataclass
class Conflict:
    task_id: uuid.UUID
    conflicting_task_id: uuid.UUID
    overlap_minutes: int
    fixed: bool


def _interval(task: Task) -> tuple[datetime, datetime] | None:
    if task.start_at is None:
        return None
    end = task.due_at
    if end is None and task.estimated_minutes:
        end = task.start_at + timedelta(minutes=task.estimated_minutes)
    if end is None:
        end = task.start_at + timedelta(minutes=30)  # default slot
    return task.start_at, end


def overlap_minutes(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> int:
    latest_start = max(a[0], b[0])
    earliest_end = min(a[1], b[1])
    delta = (earliest_end - latest_start).total_seconds() / 60
    return int(delta) if delta > 0 else 0


def detect_conflicts(tasks: list[Task]) -> list[Conflict]:
    """Return pairwise overlaps among scheduled tasks (deterministic order)."""
    scheduled: list[tuple[Task, tuple[datetime, datetime]]] = [
        (t, iv) for t in tasks if (iv := _interval(t)) is not None
    ]
    conflicts: list[Conflict] = []
    for i in range(len(scheduled)):
        for j in range(i + 1, len(scheduled)):
            ta, ia = scheduled[i]
            tb, ib = scheduled[j]
            ov = overlap_minutes(ia, ib)
            if ov > 0:
                conflicts.append(
                    Conflict(
                        task_id=ta.id,
                        conflicting_task_id=tb.id,
                        overlap_minutes=ov,
                        fixed=ta.is_fixed or tb.is_fixed,
                    )
                )
    return conflicts


def get_week(
    session: Session, user_id: uuid.UUID, starts_on_utc: datetime
) -> tuple[list[Task], list[Task], list[Conflict]]:
    week_end = starts_on_utc + timedelta(days=7)
    all_open = session.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.deleted_at.is_(None),
            Task.status.in_(["todo", "in_progress"]),
            Task.type != "note",
        )
    ).all()
    events = [t for t in all_open if t.start_at and starts_on_utc <= t.start_at < week_end]
    unscheduled = [t for t in all_open if t.start_at is None]
    conflicts = detect_conflicts(events)
    return list(events), unscheduled, conflicts


def reschedule_task(
    session: Session,
    user_id: uuid.UUID,
    task: Task,
    *,
    version: int,
    start_at: datetime | None,
    due_at: datetime | None,
    by_ai: bool = False,
) -> Task:
    """Manual/user reschedule with version check. AI callers cannot move fixed events."""
    _check_version(task, version)
    if by_ai and (task.is_fixed or not task.is_ai_adjustable):
        raise ValidationError("Fixed events cannot be moved automatically", code="fixed_event")
    if due_at and start_at and due_at < start_at:
        raise ValidationError("due_at must be >= start_at", code="invalid_time")
    before = {"start_at": task.start_at.isoformat() if task.start_at else None}
    task.start_at = start_at
    task.due_at = due_at
    task.version += 1
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="ai" if by_ai else "user",
            action="task.rescheduled",
            entity_type="task",
            entity_id=task.id,
            before_summary_json=before,
            after_summary_json={"start_at": start_at.isoformat() if start_at else None},
        )
    )
    _emit(session, task, "task.updated")
    return task


def undo_reschedule(
    session: Session, user_id: uuid.UUID, task: Task, previous_start_iso: str | None
) -> Task:
    """Revert a task's start to a previous value recorded in an activity log."""
    prev = datetime.fromisoformat(previous_start_iso) if previous_start_iso else None
    task.start_at = prev
    task.version += 1
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="task.reschedule_undone",
            entity_type="task",
            entity_id=task.id,
            after_summary_json={"start_at": previous_start_iso},
        )
    )
    _emit(session, task, "task.updated")
    return task
