"""REST boundary for self-service Agent tasks."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.core.errors import NotFoundError, ValidationError
from app.db.session import get_db
from app.models.agent import AgentRun as AgentRunModel
from app.models.agent_conversation import AgentMessage as AgentMessageModel
from app.modules.agent import (
    conversation_schemas,
    conversation_service,
    planning_schemas,
    planning_service,
    report_service,
    schemas,
    service,
)
from app.modules.agent.audit import list_execution_records
from app.workers.tasks.agent import coordinate_plan, execute_conversation_turn, execute_task

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


@router.get("/tools", response_model=schemas.ToolManifest)
def list_tools(
    _user: CurrentUser = Depends(get_current_user),
) -> schemas.ToolManifest:
    return schemas.ToolManifest(
        tools=[
            schemas.ToolManifestEntry.model_validate(tool)
            for tool in service.tool_registry.safe_manifest()
        ]
    )


@router.post("/tasks", response_model=schemas.AgentTask, status_code=202)
def create_task(
    body: schemas.AgentTaskCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> schemas.AgentTask:
    scope: dict | None = None
    if body.previous_task_id is not None:
        previous = service.get_owned_task(db, user.id, body.previous_task_id)
        scope = service.inherit_conversation_scope(
            db,
            user_id=user.id,
            previous=previous,
            request_text=body.request_text,
        )
    task = service.create_agent_task(
        db,
        user_id=user.id,
        request_text=body.request_text,
        intent_key="llm.route",
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
    "/tasks/{task_id}/records",
    response_model=list[schemas.ExecutionRecord],
)
def list_records(
    task_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[schemas.ExecutionRecord]:
    task = service.get_owned_task(db, user.id, task_id)
    return [
        schemas.ExecutionRecord.model_validate(record)
        for record in list_execution_records(db, task.id)
    ]


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
    if pending.run_id is not None:
        from app.models.agent import AgentPlanStep

        plan_step = db.scalar(select(AgentPlanStep).where(AgentPlanStep.run_id == pending.run_id))
        if plan_step is not None:
            coordinate_plan.delay(str(plan_step.plan_id))
    return schemas.PendingWrite.model_validate(pending)


@router.get("/plans/{plan_id}/report", response_model=schemas.AgentTaskReport)
def get_plan_report(
    plan_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.AgentTaskReport:
    report = report_service.get_latest_owned_report(db, user_id=user.id, plan_id=plan_id)
    return schemas.AgentTaskReport.model_validate(report_service.report_payload(report))


@router.post("/plans/{plan_id}/report/regenerate", response_model=schemas.AgentTaskReport)
def regenerate_plan_report(
    plan_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> schemas.AgentTaskReport:
    report = report_service.regenerate_owned_report(db, user_id=user.id, plan_id=plan_id)
    db.commit()
    db.refresh(report)
    return schemas.AgentTaskReport.model_validate(report_service.report_payload(report))


# -- Conversations -------------------------------------------------------


@router.post(
    "/conversations",
    response_model=conversation_schemas.Conversation,
    status_code=201,
)
def create_conversation(
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> conversation_schemas.Conversation:
    conversation = conversation_service.create_conversation(db, user_id=user.id)
    db.commit()
    db.refresh(conversation)
    return conversation_schemas.Conversation.model_validate(conversation)


@router.get(
    "/conversations",
    response_model=list[conversation_schemas.Conversation],
)
def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    status: conversation_schemas.ConversationStatus | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[conversation_schemas.Conversation]:
    conversations = conversation_service.list_owned_conversations(
        db,
        user.id,
        status=status.value if status is not None else None,
        limit=limit,
    )
    return [conversation_schemas.Conversation.model_validate(c) for c in conversations]


@router.get(
    "/conversations/{conversation_id}",
    response_model=conversation_schemas.ConversationDetail,
)
def get_conversation(
    conversation_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> conversation_schemas.ConversationDetail:
    conversation = conversation_service.get_owned_conversation(db, user.id, conversation_id)
    active_turns = conversation_service.list_active_turns(db, user.id, conversation_id)
    detail = conversation_schemas.Conversation.model_validate(conversation).model_dump()
    return conversation_schemas.ConversationDetail(
        **detail,
        active_turns=[conversation_schemas.Turn.model_validate(t) for t in active_turns],
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=conversation_schemas.TurnAccepted,
    status_code=202,
)
def submit_message(
    conversation_id: uuid.UUID,
    body: conversation_schemas.MessageCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> conversation_schemas.TurnAccepted:
    turn = conversation_service.accept_message(
        db,
        user_id=user.id,
        conversation_id=conversation_id,
        client_message_id=body.client_message_id,
        text=body.text,
    )
    db.commit()
    db.refresh(turn)
    user_message = db.get(AgentMessageModel, turn.user_message_id)
    if user_message is None:  # pragma: no cover - guarded by the FK contract
        raise NotFoundError("Message not found")
    execute_conversation_turn.delay(str(turn.id))
    return conversation_schemas.TurnAccepted(
        message=conversation_schemas.Message.model_validate(user_message),
        turn=conversation_schemas.Turn.model_validate(turn),
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=conversation_schemas.MessagePage,
)
def list_messages(
    conversation_id: uuid.UUID,
    cursor: str | None = None,
    before: str | None = None,
    latest: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> conversation_schemas.MessagePage:
    if cursor and (before or latest):
        raise ValidationError(
            "Choose either forward polling or recent history pagination",
            code="agent_message_cursor_conflict",
        )
    parsed_cursor: uuid.UUID | None = None
    if cursor:
        try:
            parsed_cursor = uuid.UUID(cursor)
        except ValueError as exc:
            raise ValidationError(
                "Invalid pagination cursor", code="agent_message_cursor_invalid"
            ) from exc
    parsed_before: uuid.UUID | None = None
    if before:
        try:
            parsed_before = uuid.UUID(before)
        except ValueError as exc:
            raise ValidationError(
                "Invalid history cursor", code="agent_message_cursor_invalid"
            ) from exc
    if latest or parsed_before is not None:
        messages, next_cursor = conversation_service.list_recent_conversation_messages(
            db,
            user.id,
            conversation_id,
            before=parsed_before,
            limit=limit,
        )
    else:
        messages, next_cursor = conversation_service.list_conversation_messages(
            db,
            user.id,
            conversation_id,
            cursor=parsed_cursor,
            limit=limit,
        )
    return conversation_schemas.MessagePage(
        items=[conversation_schemas.Message.model_validate(m) for m in messages],
        next_cursor=str(next_cursor) if next_cursor is not None else None,
    )


@router.get(
    "/conversations/{conversation_id}/plans",
    response_model=list[planning_schemas.AgentPlanView],
)
def list_conversation_plans(
    conversation_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=50),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[planning_schemas.AgentPlanView]:
    conversation_service.get_owned_conversation(db, user.id, conversation_id)
    return [
        planning_service.serialize_plan(db, plan)
        for plan in reversed(
            planning_service.list_conversation_plans(db, user.id, conversation_id, limit=limit)
        )
    ]


@router.get("/turns/{turn_id}/plan", response_model=planning_schemas.AgentPlanView)
def get_turn_plan(
    turn_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> planning_schemas.AgentPlanView:
    conversation_service.get_owned_turn(db, user.id, turn_id)
    return planning_service.serialize_plan(db, planning_service.plan_for_turn(db, user.id, turn_id))


@router.get("/plans/{plan_id}", response_model=planning_schemas.AgentPlanView)
def get_plan(
    plan_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> planning_schemas.AgentPlanView:
    return planning_service.serialize_plan(
        db, planning_service.get_owned_plan(db, user.id, plan_id)
    )


@router.post(
    "/plans/{plan_id}/retry",
    response_model=planning_schemas.AgentPlanView,
    status_code=202,
)
def retry_plan(
    plan_id: uuid.UUID,
    _body: planning_schemas.PlanRetryRequest,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> planning_schemas.AgentPlanView:
    from app.modules.agent.scheduler import retry_failed_chain

    plan = retry_failed_chain(db, user_id=user.id, plan_id=plan_id)
    db.commit()
    db.refresh(plan)
    result = planning_service.serialize_plan(db, plan)
    coordinate_plan.delay(str(plan.id))
    return result


@router.post(
    "/plans/{plan_id}/cancel",
    response_model=planning_schemas.AgentPlanView,
    status_code=202,
)
def cancel_plan(
    plan_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> planning_schemas.AgentPlanView:
    plan = planning_service.cancel_plan(db, user_id=user.id, plan_id=plan_id)
    db.commit()
    db.refresh(plan)
    result = planning_service.serialize_plan(db, plan)
    coordinate_plan.delay(str(plan.id))
    return result


@router.get("/capabilities")
def list_capabilities(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    connections = conversation_service.sync_mcp_connections(db, user_id=user.id)
    manifest = service.tool_registry.safe_manifest_v2(session=db, user_id=user.id)
    db.commit()
    return {
        **manifest,
        "connections": [
            {
                "config_key": item.config_key,
                "display_name": item.display_name,
                "health_status": item.health_status,
                "last_error_code": item.last_error_code,
            }
            for item in connections
        ],
    }


@router.get("/turns/{turn_id}", response_model=conversation_schemas.Turn)
def get_turn(
    turn_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> conversation_schemas.Turn:
    return conversation_schemas.Turn.model_validate(
        conversation_service.get_owned_turn(db, user.id, turn_id)
    )


@router.post(
    "/turns/{turn_id}/retry",
    response_model=conversation_schemas.TurnAccepted,
    status_code=202,
)
def retry_turn(
    turn_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> conversation_schemas.TurnAccepted:
    turn = conversation_service.retry_turn(db, user_id=user.id, turn_id=turn_id)
    message = db.get(AgentMessageModel, turn.user_message_id)
    if message is None:  # pragma: no cover
        raise NotFoundError("Message not found")
    db.commit()
    execute_conversation_turn.delay(str(turn.id))
    return conversation_schemas.TurnAccepted(
        message=conversation_schemas.Message.model_validate(message),
        turn=conversation_schemas.Turn.model_validate(turn),
    )
