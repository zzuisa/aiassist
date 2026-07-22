"""Plain recurring-task templates and idempotent occurrence generation (T141).

A template task has a recurrence_rule and no recurrence_parent_id. Instances are
created per local date with recurrence_parent_id + occurrence_date, unique via
`(user_id, recurrence_parent_id, occurrence_date)`. Instances inherit fixed-event
properties and are independent tasks afterwards.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.foundation import User
from app.models.tasks import Task
from app.modules.habits.recurrence import occurs_on
from app.services.outbox.publisher import append_event


def list_templates(session: Session, user_id: uuid.UUID) -> list[Task]:
    return list(
        session.scalars(
            select(Task).where(
                Task.user_id == user_id,
                Task.deleted_at.is_(None),
                Task.recurrence_rule.is_not(None),
                Task.recurrence_parent_id.is_(None),
                Task.type != "habit_task",
            )
        ).all()
    )


def generate_occurrence(session: Session, template: Task, local_date: date) -> Task | None:
    """Idempotently create one instance for local_date. Returns it or None."""
    if not template.recurrence_rule:
        return None
    if not occurs_on(template.recurrence_rule, local_date):
        return None
    existing = session.scalar(
        select(Task).where(
            Task.user_id == template.user_id,
            Task.recurrence_parent_id == template.id,
            Task.occurrence_date == local_date,
        )
    )
    if existing is not None:
        return existing

    instance = Task(
        id=uuid.uuid4(),
        user_id=template.user_id,
        type=template.type,
        title=template.title,
        description=template.description,
        status="todo",
        priority=template.priority,
        importance=template.importance,
        estimated_minutes=template.estimated_minutes,
        category_id=template.category_id,
        is_fixed=template.is_fixed,
        is_ai_adjustable=template.is_ai_adjustable,
        is_splittable=template.is_splittable,
        energy_level=template.energy_level,
        recurrence_parent_id=template.id,
        occurrence_date=local_date,
        source_type="task_recurrence",
        source_id=template.id,
    )
    session.add(instance)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return session.scalar(
            select(Task).where(
                Task.user_id == template.user_id,
                Task.recurrence_parent_id == template.id,
                Task.occurrence_date == local_date,
            )
        )
    append_event(
        session,
        event_type="task.recurrence_generated",
        aggregate_type="task",
        aggregate_id=instance.id,
        routing_key="search.index.task.created",
        payload={"task_id": str(instance.id), "template_id": str(template.id)},
        user_id=template.user_id,
    )
    return instance


def generate_for_user(session: Session, user: User, today: date | None = None) -> int:
    """Generate occurrences within the lookahead window for a user."""
    tz = ZoneInfo(user.timezone)
    today = today or datetime.now(UTC).astimezone(tz).date()
    lookahead = get_settings().recurrence_lookahead_days
    count = 0
    for template in list_templates(session, user.id):
        for offset in range(lookahead):
            d = today + timedelta(days=offset)
            if generate_occurrence(session, template, d) is not None:
                count += 1
    return count


def idempotency_key(template_id: uuid.UUID, local_date: date) -> str:
    return f"task_recurrence:{template_id}:{local_date.isoformat()}"
