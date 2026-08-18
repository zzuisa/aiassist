"""Conversation task routing preserves explicit scope and clarification linkage."""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.integration]


def _outcome(*, tool="posts.list_recent", operation="query", source="current_message", ids=None):
    from app.modules.agent.conversation_router import RoutingOutcome
    from app.modules.agent.conversation_schemas import ConversationRoute

    route = ConversationRoute.model_validate(
        {
            "schema_version": "conversation-route.v1",
            "route_kind": "task",
            "objective": "处理文章",
            "operation_type": operation,
            "target_scope": {"source": source, "object_type": "post", "object_ids": ids or []},
            "semantic_arguments": {"limit": 2},
            "candidate_tool_keys": [tool],
            "clarification_question": None,
            "requires_confirmation": operation == "update",
            "confidence": 0.95,
        }
    )
    return RoutingOutcome(route, tool)


def test_task_route_bridges_to_existing_agent_task_and_updates_context(
    db_session, make_user, monkeypatch
) -> None:
    from app.models.agent import AgentExecutionPlan, AgentTask
    from app.models.posts import Post
    from app.modules.agent import conversation_router, scheduler, step_executor
    from app.modules.agent.conversation_service import (
        accept_message,
        create_conversation,
        execute_turn,
    )
    from sqlalchemy import select

    user = make_user()
    db_session.add_all(
        [
            Post(user_id=user.id, title=f"文章 {i}", markdown="正文", status="private")
            for i in range(3)
        ]
    )
    conversation = create_conversation(db_session, user_id=user.id)
    db_session.commit()
    turn = accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id="route-query",
        text="给我最近 2 篇文章",
    )
    db_session.commit()
    monkeypatch.setattr(conversation_router, "route_message", lambda *_args, **_kwargs: _outcome())

    planned = execute_turn(db_session, turn.id)
    db_session.commit()

    assert planned.status == "executing"
    assert planned.agent_task_id is not None
    plan = db_session.scalar(
        select(AgentExecutionPlan).where(AgentExecutionPlan.turn_id == planned.id)
    )
    assert plan is not None
    ready = scheduler.coordinate_plan(db_session, plan.id)
    assert len(ready) == 1
    assert scheduler.start_step(db_session, ready[0]) is not None
    step_executor.execute_step(db_session, ready[0])
    assert scheduler.coordinate_plan(db_session, plan.id) == []
    db_session.commit()

    db_session.refresh(planned)
    finished = planned
    assert finished.status == "success"
    assert finished.agent_task_id is not None
    task = db_session.get(AgentTask, finished.agent_task_id)
    assert task is not None and task.intent_key == "articles.list_recent"
    assert len(task.scope_json["object_ids"]) == 2
    db_session.refresh(conversation)
    assert conversation.context_json["object_ids"] == task.scope_json["object_ids"]


def test_context_scope_is_copied_exactly_for_follow_up(db_session, make_user, monkeypatch) -> None:
    from app.models.agent import AgentTask
    from app.modules.agent import conversation_router
    from app.modules.agent.conversation_service import (
        accept_message,
        create_conversation,
        execute_turn,
    )

    user = make_user()
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    conversation = create_conversation(db_session, user_id=user.id)
    conversation.context_json = {
        "object_type": "post",
        "object_ids": ids,
        "object_versions": {},
        "query_conditions": {"limit": 2},
    }
    db_session.commit()
    turn = accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id="route-follow",
        text="分析刚才那些文章",
    )
    db_session.commit()
    monkeypatch.setattr(
        conversation_router,
        "route_message",
        lambda *_args, **_kwargs: _outcome(
            tool="content.extract_metadata",
            operation="analyze",
            source="conversation_context",
            ids=ids,
        ),
    )
    monkeypatch.setattr(
        "app.modules.agent.service.execute_agent_task",
        lambda _session, task_id: _session.get(AgentTask, task_id),
    )

    execute_turn(db_session, turn.id)
    task = db_session.get(AgentTask, turn.agent_task_id)
    assert task is not None
    assert task.scope_json["object_ids"] == ids


def test_clarification_is_persisted_and_next_message_links_to_waiting_turn(
    db_session, make_user, monkeypatch
) -> None:
    from app.models.agent_conversation import AgentMessage
    from app.modules.agent import conversation_router
    from app.modules.agent.conversation_router import RoutingOutcome
    from app.modules.agent.conversation_schemas import ConversationRoute
    from app.modules.agent.conversation_service import (
        accept_message,
        create_conversation,
        execute_turn,
    )

    user = make_user()
    conversation = create_conversation(db_session, user_id=user.id)
    first = accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id="clarify-1",
        text="处理文章",
    )
    db_session.commit()
    route = ConversationRoute.model_validate(
        {
            "schema_version": "conversation-route.v1",
            "route_kind": "clarification",
            "objective": "确认范围",
            "operation_type": "none",
            "target_scope": {"source": "none", "object_type": None, "object_ids": []},
            "semantic_arguments": {},
            "candidate_tool_keys": [],
            "clarification_question": "需要处理哪几篇文章？",
            "requires_confirmation": False,
            "confidence": 0.8,
        }
    )
    monkeypatch.setattr(
        conversation_router, "route_message", lambda *_args, **_kwargs: RoutingOutcome(route, None)
    )
    waiting = execute_turn(db_session, first.id)
    db_session.commit()
    assert waiting.status == "waiting_clarification"
    assert db_session.get(AgentMessage, waiting.assistant_message_id).kind == "clarification"

    next_turn = accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id="clarify-2",
        text="最近两篇",
    )
    assert next_turn.retry_of_id == waiting.id
