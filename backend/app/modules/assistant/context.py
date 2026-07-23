"""Assistant intent registry + authorized context loaders.

Each intent declares which owned entities it may read. Loaders return bounded,
provenance-aware DTOs (id + version + minimal fields) so the model is grounded in
real data and can reference only supplied IDs. No-result cases are explicit so the
assistant states "not found" instead of inventing records.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tasks import Task


@dataclass
class GroundedContext:
    entity_refs: list[dict] = field(default_factory=list)
    payload: dict = field(default_factory=dict)
    empty: bool = False


def load_today_tasks(session: Session, user_id: uuid.UUID) -> GroundedContext:
    tasks = session.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.deleted_at.is_(None),
            Task.status.in_(["todo", "in_progress"]),
        )
    ).all()
    if not tasks:
        return GroundedContext(empty=True)
    refs = [{"type": "task", "id": str(t.id), "version": t.version} for t in tasks]
    payload = {
        "tasks": [
            {
                "id": str(t.id),
                "version": t.version,
                "title": t.title,
                "start_at": t.start_at.isoformat() if t.start_at else None,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "is_fixed": t.is_fixed,  # fixed events must not be moved
                "is_ai_adjustable": t.is_ai_adjustable,
                "priority": t.priority,
                "importance": t.importance,
            }
            for t in tasks
        ]
    }
    return GroundedContext(entity_refs=refs, payload=payload)


# Intent registry: intent -> context loader. Intents without a loader are
# handled generically (no grounded entities).
INTENT_LOADERS = {
    "plan_today": load_today_tasks,
    "adjust_week": load_today_tasks,
}


def load_context(session: Session, user_id: uuid.UUID, intent: str) -> GroundedContext:
    loader = INTENT_LOADERS.get(intent)
    if loader is None:
        return GroundedContext(empty=True)
    return loader(session, user_id)
