"""Habit CRUD, check-in/skip, stats endpoints."""

from __future__ import annotations

import uuid
from datetime import date, time

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.modules.habits import service

router = APIRouter(prefix="/habits", tags=["habits"])


class HabitCreate(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    recurrence_rule: str
    suggested_time_local: time | None = None
    target_minutes: int | None = Field(default=None, ge=0)
    minimum_amount: float | None = Field(default=None, ge=0)
    unit: str | None = None
    priority: int = Field(default=0, ge=0, le=4)
    auto_create_task: bool = True
    is_ai_adjustable: bool = True


class CheckInBody(BaseModel):
    model_config = {"extra": "forbid"}
    local_date: date
    status: str = Field(pattern="^(completed|partial)$")
    amount: float | None = Field(default=None, ge=0)
    duration_seconds: int | None = Field(default=None, ge=0)


class SkipBody(BaseModel):
    model_config = {"extra": "forbid"}
    local_date: date
    reason: str = Field(pattern="^(no_time|too_tired|forgot|unrealistic_plan|not_suitable|other)$")
    note: str | None = Field(default=None, max_length=500)


def _habit_out(h) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": str(h.id),
        "name": h.name,
        "description": h.description,
        "recurrence_rule": h.recurrence_rule,
        "suggested_time_local": h.suggested_time_local.isoformat()
        if h.suggested_time_local
        else None,
        "target_minutes": h.target_minutes,
        "minimum_amount": float(h.minimum_amount) if h.minimum_amount is not None else None,
        "unit": h.unit,
        "priority": h.priority,
        "auto_create_task": h.auto_create_task,
        "is_ai_adjustable": h.is_ai_adjustable,
        "status": h.status,
        "version": h.version,
    }


def _log_out(log) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": str(log.id),
        "habit_id": str(log.habit_id),
        "local_date": log.local_date.isoformat(),
        "status": log.status,
        "amount": float(log.amount) if log.amount is not None else None,
        "duration_seconds": log.duration_seconds,
        "skip_reason": log.skip_reason,
        "skip_note": log.skip_note,
    }


@router.get("")
def list_habits(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict]:
    return [_habit_out(h) for h in service.list_habits(db, user.id)]


@router.post("", status_code=201)
def create_habit(
    body: HabitCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    habit = service.create_habit(db, user.id, body.model_dump())
    db.commit()
    return _habit_out(habit)


@router.get("/stats")
def get_stats(
    from_: date = Query(alias="from"),
    to: date = Query(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return service.compute_stats(db, user.id, from_, to)


@router.get("/{habit_id}")
def get_habit(
    habit_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return _habit_out(service.get_habit(db, user.id, habit_id))


@router.patch("/{habit_id}")
def update_habit(
    habit_id: uuid.UUID,
    body: HabitCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    habit = service.get_habit(db, user.id, habit_id)
    for k, v in body.model_dump().items():
        setattr(habit, k, v)
    habit.version += 1
    db.commit()
    return _habit_out(habit)


@router.delete("/{habit_id}", status_code=204)
def delete_habit(
    habit_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    service.archive_habit(db, user.id, habit_id)
    db.commit()
    return Response(status_code=204)


@router.post("/{habit_id}/check-ins")
def check_in(
    habit_id: uuid.UUID,
    body: CheckInBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    log = service.check_in(
        db,
        user.id,
        habit_id,
        body.local_date,
        status=body.status,
        amount=body.amount,
        duration_seconds=body.duration_seconds,
    )
    db.commit()
    return _log_out(log)


@router.post("/{habit_id}/skip")
def skip(
    habit_id: uuid.UUID,
    body: SkipBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    log = service.skip(db, user.id, habit_id, body.local_date, reason=body.reason, note=body.note)
    db.commit()
    return _log_out(log)
