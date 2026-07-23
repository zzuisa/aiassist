"""Assistant run/status/action endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.modules.assistant import service

router = APIRouter(prefix="/assistant", tags=["assistant"])

_INTENTS = (
    "plan_today|adjust_week|find_capture|find_post|analyze_habit|"
    "split_task|generate_steps|summarize_day|create_blog"
)


class RunCreate(BaseModel):
    model_config = {"extra": "forbid"}
    intent: str = Field(pattern=f"^({_INTENTS})$")
    instruction: str | None = Field(default=None, max_length=4000)
    scope_refs: list[dict] = Field(default_factory=list, max_length=100)


@router.post("/runs", status_code=202)
def create_run(
    body: RunCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    run = service.create_run(db, user.id, body.intent, body.instruction)
    db.commit()
    return run


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return service.get_run(user.id, run_id)


@router.post("/runs/{run_id}/actions/{action_id:path}")
def execute_action(
    run_id: str,
    action_id: str,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    return service.execute_action(db, user.id, run_id, action_id)
