"""Pure scheduling domain logic: conflict detection and interval overlap."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.tasks import Task
from app.modules.tasks.calendar_service import detect_conflicts, overlap_minutes

pytestmark = [pytest.mark.unit]


def _task(start: datetime, minutes: int, *, fixed: bool = False) -> Task:
    t = Task(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        type="fixed_event" if fixed else "task",
        title="t",
        status="todo",
        start_at=start,
        estimated_minutes=minutes,
        is_fixed=fixed,
        is_ai_adjustable=not fixed,
        version=1,
    )
    return t


def test_overlap_minutes_basic():
    base = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
    a = (base, base + timedelta(minutes=60))
    b = (base + timedelta(minutes=30), base + timedelta(minutes=90))
    assert overlap_minutes(a, b) == 30


def test_no_overlap_returns_zero():
    base = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
    a = (base, base + timedelta(minutes=30))
    b = (base + timedelta(minutes=30), base + timedelta(minutes=60))
    assert overlap_minutes(a, b) == 0


def test_detect_conflicts_flags_fixed():
    base = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
    a = _task(base, 60, fixed=True)
    b = _task(base + timedelta(minutes=30), 60)
    conflicts = detect_conflicts([a, b])
    assert len(conflicts) == 1
    assert conflicts[0].overlap_minutes == 30
    assert conflicts[0].fixed is True


def test_detect_conflicts_none_when_disjoint():
    base = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
    a = _task(base, 30)
    b = _task(base + timedelta(hours=2), 30)
    assert detect_conflicts([a, b]) == []


def test_unscheduled_tasks_ignored():
    base = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
    a = _task(base, 30)
    b = Task(
        id=uuid.uuid4(), user_id=uuid.uuid4(), type="task", title="u", status="todo", version=1
    )
    assert detect_conflicts([a, b]) == []
