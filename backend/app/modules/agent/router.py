"""REST boundary for self-service Agent tasks."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.models.agent import AgentRun as AgentRunModel
from app.modules.agent import schemas, service
from app.modules.agent.intents import classify_request
from app.workers.tasks.agent import execute_task

router = APIRouter(prefix="/agent", tags=["agent"])


def _task_out(task: object) -> schemas.AgentTask:
    return schemas.AgentTask.model_validate(task)


def _run_out(run: AgentRunModel) -> schemas.AgentRun:
    current = run.progress_current
    total = run.progress_total
    stage = run.stage_label
    progress = (
        schemas.Progress(current=current, total=total, stage_label=stage)
        if current is not None and total is not None
        else None
    )
    return schemas.AgentRun(
        agent_id=run.id,
        parent_agent_id=run.parent_run_id,
        agent_key=run.agent_key,
        agent_version=run.agent_version,
        agent_name=run.agent_name,
        responsibility=run.responsibility,
        current_task=run.current_task,
        status=run.status,
        current_tool=run.current_tool,
        allow_write=run.allow_write,
        progress=progress,
        result_summary=run.result_summary,
        error_message=run.error_message,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.post("/tasks", response_model=schemas.AgentTask, status_code=202)
def create_task(
    body: schemas.AgentTaskCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> schemas.AgentTask:
    intent_key = classify_request(body.request_text)
    scope: dict | None = None
    if body.previous_task_id is not None:
        previous = service.get_owned_task(db, user.id, body.previous_task_id)
        object_ids = previous.scope_json.get("object_ids", [])
        if isinstance(object_ids, list):
            scope = {"object_ids": object_ids, "previous_task_id": str(previous.id)}
    task = service.create_agent_task(
        db,
        user_id=user.id,
        request_text=body.request_text,
        intent_key=intent_key,
        scope=scope,
    )
    db.commit()
    db.refresh(task)
    execute_task.delay(str(task.id))
    return _task_out(task)


@router.get("/tasks", response_model=list[schemas.AgentTask])
def list_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    status: schemas.TaskStatus | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[schemas.AgentTask]:
    return [
        _task_out(task)
        for task in service.list_owned_tasks(
            db,
            user.id,
            status=status.value if status is not None else None,
            limit=limit,
        )
    ]


@router.get("/tasks/{task_id}", response_model=schemas.AgentTaskDetail)
def get_task(
    task_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.AgentTaskDetail:
    task = service.get_owned_task(db, user.id, task_id)
    task_data = _task_out(task).model_dump()
    return schemas.AgentTaskDetail(
        **task_data,
        runs=[_run_out(run) for run in service.task_runs(db, task.id)],
    )


@router.get(
    "/tasks/{task_id}/confirmations",
    response_model=list[schemas.PendingWrite],
)
def list_confirmations(
    task_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[schemas.PendingWrite]:
    return [
        schemas.PendingWrite.model_validate(item)
        for item in service.list_pending_writes(db, user.id, task_id)
    ]


@router.post(
    "/tasks/{task_id}/confirmations/{confirmation_id}",
    response_model=schemas.PendingWrite,
)
def decide_confirmation(
    task_id: uuid.UUID,
    confirmation_id: uuid.UUID,
    body: schemas.ConfirmationDecision,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> schemas.PendingWrite:
    pending = service.decide_pending_write(
        db,
        user_id=user.id,
        task_id=task_id,
        confirmation_id=confirmation_id,
        decision=body.decision,
    )
    db.commit()
    db.refresh(pending)
    return schemas.PendingWrite.model_validate(pending)
