"""Durable conversation/message/turn acceptance and owned lookups.

``accept_message`` is the single entry point that persists a user message and
opens its Turn. Per data-model.md Transaction Boundary §1, the Conversation
(if newly created), Message, Turn, Job, and outbox event all commit together
in the CALLER's transaction — this module never calls ``session.commit()``,
matching the convention in ``app/modules/agent/service.py``. Routing, tool
execution, and reply generation are later phases (worker Turn execution); this
module only guarantees the message/turn exist durably before any of that runs.

Every read filters by ``user_id`` — there is no cross-user visibility path.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.agent_conversation import (
    AgentConversation,
    AgentMessage,
    AgentRoutingDecision,
    AgentTurn,
    McpConnection,
    McpToolSnapshot,
)
from app.models.foundation import AsyncJob
from app.modules.agent import conversation_router
from app.modules.agent.registry import ToolContext, ToolHandler, ToolType
from app.modules.agent.status import (
    CONVERSATION_MESSAGE_CREATED,
    CONVERSATION_TURN_UPDATED,
    publish_conversation_event,
)
from app.modules.jobs import service as jobs_service
from app.services.outbox.publisher import append_event

MAX_MESSAGE_TEXT_LENGTH = 4000
DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200

# Terminal Turn states that a worker must never re-execute (idempotent replay
# guard: Celery's own at-least-once delivery plus a possible watchdog retry
# must not double-run a Turn that already finished).
_ALREADY_HANDLED_TURN_STATUSES = (
    "success",
    "partial_success",
    "failed",
    "stalled",
    "cancelled",
)


def sync_mcp_connections(
    session: Session,
    *,
    user_id: uuid.UUID,
    gateway: object | None = None,
) -> list[McpConnection]:
    """Synchronize non-secret connection/catalog metadata and runtime tools."""
    from app.modules.agent.registry import ToolDefinition, tool_registry
    from app.services.mcp.base import McpError
    from app.services.mcp.config import list_safe_mcp_metadata
    from app.services.mcp.gateway import McpGateway, get_mcp_gateway

    active_gateway = gateway if isinstance(gateway, McpGateway) else get_mcp_gateway()
    connections: list[McpConnection] = []
    for metadata in list_safe_mcp_metadata():
        connection = session.scalar(
            select(McpConnection).where(
                McpConnection.user_id == user_id,
                McpConnection.config_key == metadata.config_key,
            )
        )
        if connection is None:
            connection = McpConnection(
                user_id=user_id,
                config_key=metadata.config_key,
                display_name=metadata.display_name,
                transport=metadata.transport,
                enabled=True,
                health_status="unknown",
            )
            session.add(connection)
            session.flush()
        else:
            connection.display_name = metadata.display_name
            connection.transport = metadata.transport
        connections.append(connection)
        if not connection.enabled:
            connection.health_status = "disabled"
            continue
        try:
            discovery = active_gateway.discover(metadata.config_key)
        except McpError as exc:
            connection.health_status = "unavailable" if exc.retryable else "degraded"
            connection.last_error_code = exc.code
            connection.last_checked_at = datetime.now(UTC)
            continue
        connection.health_status = "healthy"
        connection.protocol_version = discovery.protocol_version
        connection.catalog_etag = discovery.catalog_etag
        connection.last_error_code = None
        connection.last_checked_at = datetime.now(UTC)
        catalog_payload = [
            {
                "key": item.tool_key,
                "schema": item.input_schema,
                "type": item.tool_type,
                "available": item.available,
            }
            for item in discovery.tools
        ]
        catalog_version = (
            discovery.catalog_etag
            or hashlib.sha256(
                json.dumps(catalog_payload, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()[:32]
        )
        for descriptor in discovery.tools:
            snapshot = session.scalar(
                select(McpToolSnapshot).where(
                    McpToolSnapshot.connection_id == connection.id,
                    McpToolSnapshot.tool_key == descriptor.tool_key,
                    McpToolSnapshot.catalog_version == catalog_version,
                )
            )
            if snapshot is None:
                snapshot = McpToolSnapshot(
                    connection_id=connection.id,
                    tool_key=descriptor.tool_key,
                    remote_name=descriptor.remote_name,
                    responsibility=descriptor.responsibility,
                    tool_type=descriptor.tool_type,
                    input_schema_json=descriptor.input_schema,
                    output_schema_json=descriptor.output_schema,
                    risk_json=descriptor.risk,
                    available=descriptor.available,
                    unavailable_reason=descriptor.unavailable_reason,
                    catalog_version=catalog_version,
                )
                session.add(snapshot)
            tool_registry.register_or_replace(
                ToolDefinition(
                    name=descriptor.tool_key,
                    type=cast(ToolType, descriptor.tool_type),
                    responsibility=descriptor.responsibility,
                    handler=_mcp_handler(
                        gateway=active_gateway,
                        config_key=metadata.config_key,
                        remote_name=descriptor.remote_name,
                        tool_type=descriptor.tool_type,
                    ),
                    required_permission="mcp:invoke",
                    available=descriptor.available,
                    unavailable_reason=descriptor.unavailable_reason,
                    source="mcp",
                    input_schema=descriptor.input_schema,
                    risk=descriptor.risk,
                    connection_id=connection.id,
                )
            )
    session.flush()
    return connections


def _mcp_handler(
    *, gateway: object, config_key: str, remote_name: str, tool_type: str
) -> ToolHandler:
    from app.services.mcp.gateway import McpGateway

    active_gateway = gateway
    if not isinstance(active_gateway, McpGateway):  # pragma: no cover - guarded by bootstrap
        raise TypeError("Invalid MCP gateway")

    def invoke(context: ToolContext, params: Mapping[str, Any]) -> dict[str, Any]:
        arguments = dict(params)
        if tool_type == "write":
            from app.models.agent import PendingWrite

            confirmation_id = uuid.UUID(str(arguments.pop("confirmation_id")))
            pending = context.session.get(PendingWrite, confirmation_id)
            if pending is None:
                raise ValidationError(
                    "MCP write preview not found",
                    code="agent_write_preview_invalid",
                )
            arguments = dict(pending.preview_json.get("arguments", {}))
        result = active_gateway.call_tool(
            config_key,
            remote_name,
            arguments,
            idempotency_key=f"agent-mcp:{context.task_id}:{remote_name}",
        )
        return {
            "is_error": result.is_error,
            "structured_content": result.structured_content,
            "text_summary": result.text_summary,
            "truncated": result.truncated,
        }

    return invoke


def create_conversation(
    session: Session,
    *,
    user_id: uuid.UUID,
    title: str | None = None,
) -> AgentConversation:
    conversation = AgentConversation(
        user_id=user_id,
        title=title,
        status="active",
        context_json={},
    )
    session.add(conversation)
    session.flush()
    return conversation


def get_owned_conversation(
    session: Session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> AgentConversation:
    conversation = session.get(AgentConversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise NotFoundError("Conversation not found")
    return conversation


def list_owned_conversations(
    session: Session,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> list[AgentConversation]:
    limit = min(max(limit, 1), MAX_PAGE_LIMIT)
    stmt = select(AgentConversation).where(AgentConversation.user_id == user_id)
    if status is not None:
        stmt = stmt.where(AgentConversation.status == status)
    stmt = stmt.order_by(
        AgentConversation.last_message_at.desc().nulls_last(),
        AgentConversation.created_at.desc(),
    ).limit(limit)
    return list(session.scalars(stmt).all())


def get_owned_turn(session: Session, user_id: uuid.UUID, turn_id: uuid.UUID) -> AgentTurn:
    turn = session.get(AgentTurn, turn_id)
    if turn is None:
        raise NotFoundError("Turn not found")
    conversation = session.get(AgentConversation, turn.conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise NotFoundError("Turn not found")
    return turn


def retry_turn(session: Session, *, user_id: uuid.UUID, turn_id: uuid.UUID) -> AgentTurn:
    """Create at most one active retry linked to an owned failed/stalled Turn."""
    from app.core.errors import ConflictError

    original = get_owned_turn(session, user_id, turn_id)
    if original.status not in {"failed", "stalled"}:
        raise ConflictError("Turn is not retryable", code="agent_turn_not_retryable")
    existing = session.scalar(
        select(AgentTurn).where(
            AgentTurn.retry_of_id == original.id,
            AgentTurn.status.notin_(("failed", "stalled", "cancelled")),
        )
    )
    if existing is not None:
        return existing
    message = session.get(AgentMessage, original.user_message_id)
    if message is None:
        raise NotFoundError("Turn message not found")
    job = jobs_service.create_job(
        session,
        user_id=user_id,
        job_type="agent.conversation_turn",
        entity_type="agent_conversation",
        entity_id=original.conversation_id,
        idempotency_key=f"agent-turn-retry:{original.id}:{original.retry_count + 1}",
        max_retries=1,
    )
    retry = AgentTurn(
        conversation_id=original.conversation_id,
        user_message_id=message.id,
        job_id=job.id,
        retry_of_id=original.id,
        retry_count=original.retry_count + 1,
        status="accepted",
    )
    session.add(retry)
    session.flush()
    return retry


def finalize_turn_failure(session: Session, turn_id: uuid.UUID, exc: Exception) -> AgentTurn | None:
    """Persist a user-visible terminal state in an independent transaction."""
    turn = session.get(AgentTurn, turn_id)
    if turn is None or turn.status in _ALREADY_HANDLED_TURN_STATUSES:
        return turn
    turn.status = "failed"
    turn.error_code = "agent_turn_execution_failed"
    turn.error_message = "处理消息时发生错误，消息已保留，可以安全重试。"
    turn.current_step = "处理失败"
    turn.finished_at = datetime.now(UTC)
    job = session.get(AsyncJob, turn.job_id)
    if job is not None:
        jobs_service.transition(
            session,
            job,
            status="failed",
            current_step="处理失败",
            error_code=turn.error_code,
            error_message=turn.error_message,
            error_retryable=True,
        )
    if turn.agent_task_id is not None:
        from app.models.agent import AgentTask

        task = session.get(AgentTask, turn.agent_task_id)
        if task is not None and task.status in {"pending", "running"}:
            task.status = "failed"
            task.finished_at = datetime.now(UTC)
    publish_conversation_event(
        session,
        turn,
        event_type=CONVERSATION_TURN_UPDATED,
        error_message=turn.error_message,
    )
    _ = exc  # raw exception text is intentionally not persisted
    session.flush()
    return turn


def list_active_turns(
    session: Session, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[AgentTurn]:
    get_owned_conversation(session, user_id, conversation_id)
    return list(
        session.scalars(
            select(AgentTurn)
            .where(
                AgentTurn.conversation_id == conversation_id,
                AgentTurn.status.notin_(("success", "partial_success", "cancelled")),
            )
            .order_by(AgentTurn.created_at)
        ).all()
    )


def list_conversation_messages(
    session: Session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    cursor: uuid.UUID | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> tuple[list[AgentMessage], uuid.UUID | None]:
    """Return one page of owned messages, oldest-after-cursor first."""
    get_owned_conversation(session, user_id, conversation_id)
    limit = min(max(limit, 1), MAX_PAGE_LIMIT)
    stmt = select(AgentMessage).where(AgentMessage.conversation_id == conversation_id)
    if cursor is not None:
        anchor = session.get(AgentMessage, cursor)
        if anchor is not None and anchor.conversation_id == conversation_id:
            stmt = stmt.where(
                tuple_(AgentMessage.created_at, AgentMessage.id)
                > tuple_(anchor.created_at, anchor.id)  # type: ignore[arg-type]
            )
    stmt = stmt.order_by(AgentMessage.created_at, AgentMessage.id).limit(limit + 1)
    rows = list(session.scalars(stmt).all())
    next_cursor: uuid.UUID | None = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1].id
        rows = rows[:limit]
    return rows, next_cursor


def _find_turn_for_client_message(
    session: Session,
    user_id: uuid.UUID,
    client_message_id: str,
) -> AgentTurn | None:
    message = session.scalar(
        select(AgentMessage).where(
            AgentMessage.user_id == user_id,
            AgentMessage.client_message_id == client_message_id,
        )
    )
    if message is None:
        return None
    turn = session.scalar(select(AgentTurn).where(AgentTurn.user_message_id == message.id))
    return turn


def accept_message(
    session: Session,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    client_message_id: str,
    text: str,
) -> AgentTurn:
    """Durably accept one user message, idempotent on ``client_message_id``.

    Creates the AgentMessage, its AgentTurn, a paired AsyncJob, and an outbox
    event in this single caller-owned transaction. A retried delivery with the
    same ``client_message_id`` for this user returns the SAME Turn rather than
    creating a duplicate — no model/tool call has necessarily happened yet,
    but the durable record is guaranteed to exist exactly once.
    """
    normalized = text.strip()
    if not normalized:
        raise ValidationError("Message text is required", code="agent_message_text_empty")
    if len(normalized) > MAX_MESSAGE_TEXT_LENGTH:
        raise ValidationError("Message text is too long", code="agent_message_text_too_long")
    client_message_id = client_message_id.strip()
    if not client_message_id:
        raise ValidationError("client_message_id is required", code="agent_client_message_id_empty")

    conversation = get_owned_conversation(session, user_id, conversation_id)

    waiting_clarification = session.scalar(
        select(AgentTurn)
        .where(
            AgentTurn.conversation_id == conversation_id,
            AgentTurn.status == "waiting_clarification",
        )
        .order_by(AgentTurn.created_at.desc())
        .limit(1)
    )

    existing_turn = _find_turn_for_client_message(session, user_id, client_message_id)
    if existing_turn is not None:
        if existing_turn.conversation_id != conversation_id:
            raise ValidationError(
                "client_message_id was already used in a different conversation",
                code="agent_client_message_id_conflict",
            )
        return existing_turn

    message = AgentMessage(
        conversation_id=conversation.id,
        user_id=user_id,
        role="user",
        kind="text",
        content_json={"text": normalized},
        client_message_id=client_message_id,
    )
    session.add(message)
    session.flush()

    job = jobs_service.create_job(
        session,
        user_id=user_id,
        job_type="agent.conversation_turn",
        entity_type="agent_conversation",
        entity_id=conversation.id,
        idempotency_key=f"agent-turn:{user_id}:{client_message_id}",
        max_retries=1,
    )

    turn = AgentTurn(
        conversation_id=conversation.id,
        user_message_id=message.id,
        job_id=job.id,
        status="accepted",
        retry_count=0,
        retry_of_id=waiting_clarification.id if waiting_clarification is not None else None,
    )
    session.add(turn)
    session.flush()

    now = datetime.now(UTC)
    conversation.last_message_at = now
    conversation.status = "active"

    append_event(
        session,
        event_type="agent.turn_accepted",
        aggregate_type="agent_turn",
        aggregate_id=turn.id,
        routing_key="agent.conversation",
        payload={
            "turn_id": str(turn.id),
            "conversation_id": str(conversation.id),
            "user_message_id": str(message.id),
            "job_id": str(job.id),
        },
        user_id=user_id,
    )
    session.flush()
    return turn


def execute_turn(session: Session, turn_id: uuid.UUID) -> AgentTurn:
    """Worker entry point: route and finalize exactly one Turn.

    This phase (US1) only implements the deterministic fast path — pure
    greeting/thanks/goodbye/capability-help — with ZERO side effects beyond
    the assistant reply itself: no AgentTask, no ExecutionRecord, no business
    table write. A message that is NOT fast-path-answerable is left in a
    clearly-marked terminal ``failed`` state with a stable error_code rather
    than crashing or fabricating a task; Phase 4 (US2) replaces that branch
    with real structured LLM-based task routing.

    Idempotent: re-invoking on an already-terminal Turn is a no-op, so a
    redelivered Celery task or a future watchdog retry cannot double-post the
    assistant reply or double-transition the paired Job.
    """
    turn = session.get(AgentTurn, turn_id)
    if turn is None:
        raise NotFoundError("Turn not found")
    if turn.status in _ALREADY_HANDLED_TURN_STATUSES:
        return turn

    conversation = session.get(AgentConversation, turn.conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found")
    user_message = session.get(AgentMessage, turn.user_message_id)
    if user_message is None:
        raise NotFoundError("User message not found")

    job = session.get(AsyncJob, turn.job_id)
    now = datetime.now(UTC)
    text = str(user_message.content_json.get("text", ""))
    fast_path_kind = conversation_router.classify_fast_path(text)

    if fast_path_kind is not None:
        reply_text = conversation_router.build_fast_path_reply(
            fast_path_kind, session=session, user_id=conversation.user_id
        )
        assistant_message = AgentMessage(
            conversation_id=turn.conversation_id,
            user_id=conversation.user_id,
            role="assistant",
            kind="text",
            content_json={"text": reply_text},
            reply_to_id=user_message.id,
        )
        session.add(assistant_message)
        session.flush()

        turn.assistant_message_id = assistant_message.id
        turn.route_kind = conversation_router.route_kind_for(fast_path_kind)
        turn.status = "success"
        turn.current_step = "已回复"
        turn.finished_at = now
        session.flush()

        if job is not None:
            jobs_service.transition(
                session,
                job,
                status="completed",
                progress=100,
                current_step="已回复",
                result={"turn_id": str(turn.id), "route_kind": turn.route_kind},
            )

        publish_conversation_event(
            session,
            turn,
            event_type=CONVERSATION_MESSAGE_CREATED,
            message_id=assistant_message.id,
        )
        publish_conversation_event(
            session,
            turn,
            event_type=CONVERSATION_TURN_UPDATED,
            result_summary=reply_text,
        )
        conversation.last_message_at = now
        session.flush()
        return turn

    # All non-fast-path messages use the versioned structured router and then a
    # deterministic policy check. A clarification answer includes the original
    # request, but never expands the previously recorded object scope.
    route_text = text
    parent_turn: AgentTurn | None = None
    if turn.retry_of_id is not None:
        parent_turn = session.get(AgentTurn, turn.retry_of_id)
        if parent_turn is not None:
            parent_message = session.get(AgentMessage, parent_turn.user_message_id)
            if parent_message is not None:
                original = str(parent_message.content_json.get("text", ""))
                route_text = f"原请求：{original}\n用户补充：{text}"

    turn.status = "routing"
    turn.current_step = "正在理解请求"
    turn.last_heartbeat_at = now
    if job is not None:
        jobs_service.transition(
            session,
            job,
            status="processing",
            progress=10,
            current_step="正在理解请求",
        )
    session.flush()

    sync_mcp_connections(session, user_id=conversation.user_id)
    outcome = conversation_router.route_message(
        route_text,
        session=session,
        user_id=conversation.user_id,
        context=conversation.context_json,
    )
    route = outcome.route
    decision = AgentRoutingDecision(
        turn_id=turn.id,
        schema_version=route.schema_version,
        attempt=1,
        route_kind=route.route_kind.value,
        objective=route.objective,
        operation_type=route.operation_type.value,
        target_scope_json=route.target_scope.model_dump(mode="json"),
        semantic_args_json=route.semantic_arguments,
        candidate_tools_json=list(route.candidate_tool_keys),
        selected_tool=outcome.selected_tool,
        requires_confirmation=route.requires_confirmation,
        confidence=route.confidence,
        validation_status="invalid" if outcome.validation_errors else "valid",
        validation_errors_json=list(outcome.validation_errors),
    )
    session.add(decision)
    turn.route_kind = route.route_kind.value

    if route.route_kind.value == "clarification":
        question = route.clarification_question or "请补充完成请求所需的信息。"
        assistant_message = _create_assistant_message(
            session,
            turn=turn,
            conversation=conversation,
            user_message=user_message,
            kind="clarification",
            text=question,
        )
        turn.assistant_message_id = assistant_message.id
        turn.status = "waiting_clarification"
        turn.current_step = "等待补充信息"
        if job is not None:
            jobs_service.transition(
                session,
                job,
                status="waiting_user",
                progress=20,
                current_step="等待补充信息",
                result={"turn_id": str(turn.id), "route_kind": "clarification"},
            )
        _publish_reply_events(session, turn, assistant_message, question)
        session.flush()
        return turn

    if route.route_kind.value != "task" or outcome.selected_tool is None:
        # The strict fast path owns chat/help; a model-proposed chat route is
        # answered without creating a business task, preserving that boundary.
        reply_text = "我在。请直接告诉我你希望查询或处理什么。"
        assistant_message = _create_assistant_message(
            session,
            turn=turn,
            conversation=conversation,
            user_message=user_message,
            kind="text",
            text=reply_text,
        )
        turn.assistant_message_id = assistant_message.id
        turn.status = "success"
        turn.current_step = "已回复"
        turn.finished_at = datetime.now(UTC)
        if job is not None:
            jobs_service.transition(
                session,
                job,
                status="completed",
                progress=100,
                current_step="已回复",
                result={"turn_id": str(turn.id), "route_kind": turn.route_kind},
            )
        _publish_reply_events(session, turn, assistant_message, reply_text)
        session.flush()
        return turn

    from app.modules.agent import service as agent_service

    scope = _scope_for_route(conversation.context_json, route.target_scope.model_dump(mode="json"))
    task = agent_service.create_agent_task(
        session,
        user_id=conversation.user_id,
        request_text=route_text,
        intent_key=(
            "mcp.invoke"
            if outcome.selected_tool.startswith("mcp.")
            else _intent_for_selected_tool(outcome.selected_tool)
        ),
        scope=scope,
        idempotency_key=f"conversation-task:{turn.id}",
    )
    turn.agent_task_id = task.id
    turn.status = "executing"
    turn.current_step = "正在执行任务"
    turn.last_heartbeat_at = datetime.now(UTC)
    session.flush()

    executed = (
        _execute_mcp_task(
            session,
            task=task,
            tool_name=outcome.selected_tool,
            arguments=route.semantic_arguments,
            requires_confirmation=route.requires_confirmation,
        )
        if outcome.selected_tool.startswith("mcp.")
        else agent_service.execute_agent_task(session, task.id)
    )
    task_status = executed.status
    turn.status = {
        "success": "success",
        "partial_success": "partial_success",
        "waiting_confirmation": "waiting_confirmation",
        "failed": "failed",
    }.get(task_status, "executing")
    turn.current_step = "等待确认" if turn.status == "waiting_confirmation" else "任务处理完成"
    if turn.status in {"success", "partial_success", "failed"}:
        turn.finished_at = datetime.now(UTC)

    result_text = executed.result_summary or (
        "已生成修改预览，确认前不会写入。"
        if turn.status == "waiting_confirmation"
        else "任务已受理，正在处理。"
    )
    assistant_message = _create_assistant_message(
        session,
        turn=turn,
        conversation=conversation,
        user_message=user_message,
        kind="result" if turn.status != "failed" else "error",
        text=result_text,
        extra={"task_id": str(task.id), "task_status": task_status},
    )
    turn.assistant_message_id = assistant_message.id
    if executed.scope_json:
        conversation.context_json = {
            **conversation.context_json,
            **executed.scope_json,
            "object_type": route.target_scope.object_type or "post",
            "last_task_id": str(task.id),
        }
    if parent_turn is not None and parent_turn.status == "waiting_clarification":
        parent_turn.status = "cancelled"
        parent_turn.current_step = "已由补充信息继续"
        parent_turn.finished_at = datetime.now(UTC)
        parent_job = session.get(AsyncJob, parent_turn.job_id)
        if parent_job is not None:
            jobs_service.transition(
                session,
                parent_job,
                status="cancelled",
                current_step="已由补充信息继续",
            )
    if job is not None:
        if turn.status == "waiting_confirmation":
            jobs_service.transition(
                session,
                job,
                status="waiting_user",
                progress=90,
                current_step="等待确认",
                result={"turn_id": str(turn.id), "agent_task_id": str(task.id)},
            )
        elif turn.status in {"success", "partial_success"}:
            jobs_service.transition(
                session,
                job,
                status="completed",
                progress=100,
                current_step="任务处理完成",
                result={"turn_id": str(turn.id), "agent_task_id": str(task.id)},
            )
        elif turn.status == "failed":
            jobs_service.transition(
                session,
                job,
                status="failed",
                current_step="任务处理失败",
                error_code="agent_task_failed",
                error_message="任务执行失败，请查看对话中的结果。",
                error_retryable=True,
            )
    _publish_reply_events(session, turn, assistant_message, result_text)
    session.flush()
    return turn


def _intent_for_selected_tool(tool_name: str) -> str:
    mapping = {
        "posts.list_recent": "articles.list_recent",
        "taxonomy.categories": "taxonomy.categories",
        "taxonomy.tags": "taxonomy.tags",
        "content.extract_metadata": "articles.analyze",
        "posts.apply_analysis": "articles.analyze",
    }
    return mapping.get(tool_name, "capability.unknown")


def _execute_mcp_task(
    session: Session,
    *,
    task: Any,
    tool_name: str,
    arguments: dict[str, Any],
    requires_confirmation: bool,
) -> Any:
    """Execute an authorized MCP read or create a local write preview."""
    from app.models.agent import AgentRun
    from app.modules.agent.audit import write_execution_record
    from app.modules.agent.registry import ToolContext, tool_registry

    tool = tool_registry.get(tool_name)
    now = datetime.now(UTC)
    run = AgentRun(
        task_id=task.id,
        agent_key="mcp-tool-agent",
        agent_version="conversation-route.v1",
        agent_name="外部能力 Agent",
        responsibility=tool.responsibility,
        current_task=task.request_text,
        input_scope_json=task.scope_json,
        allowed_tools=[tool_name],
        status="running",
        current_tool=tool_name,
        stage_label="正在调用已授权外部能力",
        started_at=now,
    )
    session.add(run)
    session.flush()
    task.status = "running"

    if tool.type == "write":
        if not requires_confirmation or not tool.risk.get("previewable"):
            raise ValidationError(
                "MCP write tool cannot produce a safe preview",
                code="agent_mcp_write_not_previewable",
            )
        from app.modules.agent import service as agent_service

        targets = [
            {"id": value, "version": None} for value in task.scope_json.get("object_ids", [])
        ]
        pending = agent_service.create_pending_write(
            session,
            task=task,
            run=run,
            operation_type="update",
            target_type="mcp_external",
            targets=targets,
            preview={
                "summary": "将通过已授权外部能力执行写操作",
                "tool_name": tool_name,
                "arguments": arguments,
            },
            reversible=bool(tool.risk.get("reversible")),
            tool_name=tool_name,
        )
        task.result_summary = json.dumps(
            {"status": "waiting_confirmation", "confirmation_id": str(pending.id)},
            ensure_ascii=False,
        )
        return task

    result = tool_registry.invoke(
        tool_name,
        context=ToolContext(
            user_id=task.user_id,
            task_id=task.id,
            run_id=run.id,
            session=session,
        ),
        params=arguments,
    )
    is_error = bool(result.get("is_error")) if isinstance(result, dict) else False
    write_execution_record(
        session,
        task_id=task.id,
        run_id=run.id,
        agent_name=run.agent_name,
        step_label="调用已授权 MCP 工具",
        tool_name=tool_name,
        operation_type="query",
        params=arguments,
        status="failed" if is_error else "success",
        result_summary="外部能力返回错误" if is_error else "外部能力调用完成",
    )
    finished = datetime.now(UTC)
    task.status = "failed" if is_error else "success"
    task.result_summary = json.dumps(result, ensure_ascii=False, default=str)
    task.finished_at = finished
    run.status = task.status
    run.current_tool = None
    run.stage_label = "外部能力调用完成"
    run.result_summary = "调用失败" if is_error else "调用成功"
    run.finished_at = finished
    return task


def _scope_for_route(context: dict, target_scope: dict) -> dict:
    source = target_scope.get("source")
    proposed_ids = [str(value) for value in target_scope.get("object_ids", [])]
    if source == "conversation_context":
        owned_ids = [str(value) for value in context.get("object_ids", [])]
        if proposed_ids and any(value not in owned_ids for value in proposed_ids):
            raise ValidationError(
                "Conversation route attempted to expand the prior object scope",
                code="agent_conversation_scope_expansion",
            )
        selected_ids = proposed_ids or owned_ids
        return {
            **context,
            "object_ids": selected_ids,
            "previous_task_id": context.get("last_task_id"),
        }
    return {
        "object_ids": proposed_ids,
        "object_versions": {},
        "query_conditions": {},
        "pending_write_ids": [],
        "completed_object_ids": [],
        "failed_object_ids": [],
        "valid": True,
    }


def _create_assistant_message(
    session: Session,
    *,
    turn: AgentTurn,
    conversation: AgentConversation,
    user_message: AgentMessage,
    kind: str,
    text: str,
    extra: dict | None = None,
) -> AgentMessage:
    message = AgentMessage(
        conversation_id=turn.conversation_id,
        user_id=conversation.user_id,
        role="assistant",
        kind=kind,
        content_json={"text": text, **(extra or {})},
        reply_to_id=user_message.id,
    )
    session.add(message)
    session.flush()
    conversation.last_message_at = datetime.now(UTC)
    return message


def _publish_reply_events(
    session: Session,
    turn: AgentTurn,
    message: AgentMessage,
    summary: str,
) -> None:
    publish_conversation_event(
        session,
        turn,
        event_type=CONVERSATION_MESSAGE_CREATED,
        message_id=message.id,
    )
    publish_conversation_event(
        session,
        turn,
        event_type=CONVERSATION_TURN_UPDATED,
        result_summary=summary[:1000],
    )
