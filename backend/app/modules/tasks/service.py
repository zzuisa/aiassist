"""Task application service: CRUD, optimistic concurrency, current-task ranking.

Every write persists business data + activity + outbox in one transaction and
never depends on AI/worker availability for durable acceptance (US1).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError, VersionConflictError
from app.models.foundation import ActivityLog, Tag
from app.models.tasks import Task, TaskTag
from app.modules.tasks.schemas import TaskCreate, TaskPatch
from app.services.outbox.publisher import append_event


def _activity(
    session: Session, user_id: uuid.UUID, action: str, task: Task, before: dict | None = None
) -> None:
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action=action,
            entity_type="task",
            entity_id=task.id,
            before_summary_json=before,
            after_summary_json={"title": task.title, "status": task.status},
        )
    )


def _emit(session: Session, task: Task, event_type: str) -> None:
    append_event(
        session,
        event_type=event_type,
        aggregate_type="task",
        aggregate_id=task.id,
        routing_key=f"search.index.task.{event_type.split('.')[-1]}",
        payload={"task_id": str(task.id), "entity_type": "task"},
        user_id=task.user_id,
    )


def _validate_tags(session: Session, user_id: uuid.UUID, tag_ids: list[uuid.UUID]) -> None:
    if not tag_ids:
        return
    owned = set(
        session.scalars(select(Tag.id).where(Tag.user_id == user_id, Tag.id.in_(tag_ids))).all()
    )
    missing = set(tag_ids) - owned
    if missing:
        raise ValidationError("One or more tags do not belong to the user", code="invalid_tag")


def _set_tags(session: Session, task: Task, tag_ids: list[uuid.UUID]) -> None:
    session.query(TaskTag).filter(TaskTag.task_id == task.id).delete()
    for tid in dict.fromkeys(tag_ids):
        session.add(TaskTag(task_id=task.id, tag_id=tid, user_id=task.user_id))


def get_tag_ids(session: Session, task_id: uuid.UUID) -> list[uuid.UUID]:
    return list(session.scalars(select(TaskTag.tag_id).where(TaskTag.task_id == task_id)).all())


def create_task(session: Session, user_id: uuid.UUID, payload: TaskCreate) -> Task:
    _validate_tags(session, user_id, payload.tag_ids)
    task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        type=payload.type,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        priority=payload.priority,
        importance=payload.importance,
        start_at=payload.start_at,
        due_at=payload.due_at,
        estimated_minutes=payload.estimated_minutes,
        category_id=payload.category_id,
        is_fixed=payload.is_fixed,
        is_ai_adjustable=False if payload.is_fixed else payload.is_ai_adjustable,
        is_splittable=payload.is_splittable,
        energy_level=payload.energy_level,
        recurrence_rule=payload.recurrence_rule,
        source_type="manual",
    )
    if payload.status == "completed":
        task.completed_at = datetime.now(UTC)
    session.add(task)
    session.flush()
    _set_tags(session, task, payload.tag_ids)
    _activity(session, user_id, "task.created", task)
    _emit(session, task, "task.created")
    return task


def get_task(session: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = session.get(Task, task_id)
    if task is None or task.user_id != user_id or task.deleted_at is not None:
        raise NotFoundError("Task not found")
    return task


def _check_version(task: Task, version: int) -> None:
    if task.version != version:
        raise VersionConflictError(
            "The task was modified by another change. Refresh and retry.",
            code="version_conflict",
        )


def update_task(
    session: Session, user_id: uuid.UUID, task_id: uuid.UUID, payload: TaskPatch, provided: set[str]
) -> Task:
    task = get_task(session, user_id, task_id)
    _check_version(task, payload.version)
    before = {"title": task.title, "status": task.status}

    for field in (
        "title",
        "description",
        "status",
        "priority",
        "importance",
        "start_at",
        "due_at",
        "estimated_minutes",
        "actual_minutes",
        "is_fixed",
        "is_ai_adjustable",
        "is_splittable",
        "energy_level",
    ):
        if field in provided:
            setattr(task, field, getattr(payload, field))

    if task.is_fixed:
        task.is_ai_adjustable = False
    if task.due_at and task.start_at and task.due_at < task.start_at:
        raise ValidationError("due_at must be >= start_at", code="invalid_time")
    if "status" in provided and task.status == "completed" and task.completed_at is None:
        task.completed_at = datetime.now(UTC)

    if "tag_ids" in provided and payload.tag_ids is not None:
        _validate_tags(session, user_id, payload.tag_ids)
        _set_tags(session, task, payload.tag_ids)

    task.version += 1
    _activity(session, user_id, "task.updated", task, before)
    _emit(session, task, "task.updated")
    return task


def complete_task(
    session: Session,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    version: int,
    actual_minutes: int | None,
) -> Task:
    task = get_task(session, user_id, task_id)
    _check_version(task, version)
    task.status = "completed"
    task.completed_at = datetime.now(UTC)
    if actual_minutes is not None:
        task.actual_minutes = actual_minutes
    task.version += 1
    _activity(session, user_id, "task.completed", task)
    _emit(session, task, "task.completed")
    return task


def delete_task(session: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> None:
    task = get_task(session, user_id, task_id)
    task.deleted_at = datetime.now(UTC)
    task.version += 1
    _activity(session, user_id, "task.deleted", task)
    _emit(session, task, "task.deleted")


def list_tasks(
    session: Session,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    limit: int = 100,
) -> list[Task]:
    stmt = select(Task).where(Task.user_id == user_id, Task.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Task.status == status)
    if from_dt:
        stmt = stmt.where(Task.start_at >= from_dt)
    if to_dt:
        stmt = stmt.where(Task.start_at <= to_dt)
    stmt = stmt.order_by(Task.created_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def select_current_task(
    session: Session, user_id: uuid.UUID, now: datetime | None = None
) -> Task | None:
    """Pick the single most-relevant open task with an explainable ranking.

    Ranking: in-progress first, then overdue, then higher importance/priority,
    then earliest due. Deterministic and independent of AI.
    """
    now = now or datetime.now(UTC)
    candidates = session.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.deleted_at.is_(None),
            Task.status.in_(["todo", "in_progress"]),
            Task.type != "note",
        )
    ).all()
    if not candidates:
        return None

    def rank(t: Task) -> tuple:
        in_progress = 0 if t.status == "in_progress" else 1
        overdue = 0 if (t.due_at and t.due_at < now) else 1
        due_key = t.due_at.timestamp() if t.due_at else float("inf")
        return (in_progress, overdue, -t.importance, -t.priority, due_key)

    return sorted(candidates, key=rank)[0]
