"""Task CRUD endpoints with optimistic-version conflict handling."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.modules.tasks import service as task_service
from app.modules.tasks.schemas import (
    TaskComplete,
    TaskCreate,
    TaskOut,
    TaskPage,
    TaskPatch,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _out(session: Session, task) -> TaskOut:  # type: ignore[no-untyped-def]
    return TaskOut.from_model(task, task_service.get_tag_ids(session, task.id))


@router.get("", response_model=TaskPage)
def list_tasks(
    status: str | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskPage:
    tasks = task_service.list_tasks(db, user.id, status=status, from_dt=from_, to_dt=to)
    return TaskPage(items=[_out(db, t) for t in tasks])


@router.post("", response_model=TaskOut, status_code=201)
def create_task(
    payload: TaskCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> TaskOut:
    task = task_service.create_task(db, user.id, payload)
    db.commit()
    return _out(db, task)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskOut:
    task = task_service.get_task(db, user.id, task_id)
    return _out(db, task)


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> TaskOut:
    raw = await request.json()
    payload = TaskPatch.model_validate(raw)
    provided = set(raw.keys())
    task = task_service.update_task(db, user.id, task_id, payload, provided)
    db.commit()
    return _out(db, task)


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    task_service.delete_task(db, user.id, task_id)
    db.commit()
    return Response(status_code=204)


@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(
    task_id: uuid.UUID,
    payload: TaskComplete = Body(...),
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> TaskOut:
    task = task_service.complete_task(db, user.id, task_id, payload.version, payload.actual_minutes)
    db.commit()
    return _out(db, task)
