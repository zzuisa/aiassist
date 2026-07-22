"""Beat-triggered habit and recurring-task generation.

The scan task fans out per-user generation commands. Generation is idempotent via
the tasks unique constraints, so duplicate Beat/worker executions are safe.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.observability import get_logger
from app.db.session import session_scope
from app.models.foundation import User
from app.modules.habits import service as habit_service
from app.modules.tasks import recurrence
from app.workers.celery_app import celery

log = get_logger("worker.habits")


@celery.task(name="app.workers.tasks.habits.scan_and_generate")
def scan_and_generate() -> None:
    """Enqueue per-user generation for all active users (Beat-triggered)."""
    with session_scope() as s:
        user_ids = [str(uid) for uid in s.scalars(select(User.id).where(User.status == "active"))]
    for uid in user_ids:
        generate_for_user.delay(uid)


@celery.task(name="app.workers.tasks.habits.generate_for_user")
def generate_for_user(user_id: str) -> int:
    with session_scope() as s:
        user = s.get(User, uuid.UUID(user_id))
        if user is None:
            return 0
        habit_count = habit_service.generate_for_user(s, user)
        recurrence_count = recurrence.generate_for_user(s, user)
    log.info("habit_generation", user_id=user_id, habits=habit_count, recurring=recurrence_count)
    return habit_count + recurrence_count
