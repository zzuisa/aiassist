"""Plain recurring-task templates: idempotent occurrence generation (T141)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from app.db.session import session_scope
from app.models.tasks import Task
from app.modules.tasks import recurrence
from app.modules.tasks import service as task_service
from app.modules.tasks.schemas import TaskCreate

pytestmark = [pytest.mark.integration]


def _template(session, user_id, **kw) -> Task:
    return task_service.create_task(
        session,
        user_id,
        TaskCreate(title="每日站会", type="task", recurrence_rule="FREQ=DAILY", **kw),
    )


def test_generation_creates_one_instance_per_date(make_user):
    user = make_user()
    d = date(2026, 7, 27)
    with session_scope() as s:
        tmpl = _template(s, user.id)
        tid = tmpl.id
        uid = user.id

    for _ in range(3):  # duplicate runs
        with session_scope() as s:
            recurrence.generate_occurrence(s, s.get(Task, tid), d)

    with session_scope() as s:
        from sqlalchemy import func, select

        count = s.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.user_id == uid,
                Task.recurrence_parent_id == tid,
                Task.occurrence_date == d,
            )
        )
        assert count == 1


def test_instance_inherits_fixed_and_is_independent(make_user):
    user = make_user()
    d = date(2026, 7, 27)
    with session_scope() as s:
        tmpl = _template(s, user.id, is_fixed=True)
        tid = tmpl.id

    with session_scope() as s:
        inst = recurrence.generate_occurrence(s, s.get(Task, tid), d)
        assert inst is not None
        assert inst.is_fixed is True
        assert inst.is_ai_adjustable is False
        assert inst.recurrence_parent_id == tid
        assert inst.source_type == "task_recurrence"


def test_soft_deleted_template_still_dedupes(make_user):
    """The unique index includes soft-deleted rows, so a deleted instance is not
    regenerated."""
    user = make_user()
    d = date(2026, 7, 27)
    with session_scope() as s:
        tmpl = _template(s, user.id)
        tid = tmpl.id
    with session_scope() as s:
        inst = recurrence.generate_occurrence(s, s.get(Task, tid), d)
        inst_id = inst.id
        inst.deleted_at = __import__("datetime").datetime.now(__import__("datetime").UTC)

    with session_scope() as s:
        again = recurrence.generate_occurrence(s, s.get(Task, tid), d)
        # Returns the existing (now-deleted) instance rather than creating a new one.
        assert again is not None
        assert again.id == inst_id


def test_idempotency_key_shape():
    tid = uuid.uuid4()
    key = recurrence.idempotency_key(tid, date(2026, 7, 27))
    assert key == f"task_recurrence:{tid}:2026-07-27"
