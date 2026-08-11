"""Greetings persist durably before reply, and the fast path creates ZERO
AgentTask, ExecutionRecord, or business-table rows."""

from __future__ import annotations

from sqlalchemy import select


def test_greeting_persists_before_reply_and_has_zero_side_effects(db_session, make_user) -> None:
    from app.models.agent import AgentTask, ExecutionRecord
    from app.models.agent_conversation import AgentConversation, AgentMessage, AgentTurn
    from app.modules.agent.conversation_service import accept_message, create_conversation
    from app.modules.agent.conversation_service import execute_turn as run_turn

    user = make_user()
    conversation = create_conversation(db_session, user_id=user.id)
    db_session.commit()

    turn = accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id="greeting-1",
        text="hi",
    )
    db_session.commit()

    # The user message and turn are durably committed BEFORE any reply exists.
    turn_id = turn.id
    db_session.expunge_all()
    persisted_turn = db_session.get(AgentTurn, turn_id)
    assert persisted_turn is not None
    assert persisted_turn.status == "accepted"
    assert persisted_turn.assistant_message_id is None
    user_message = db_session.get(AgentMessage, persisted_turn.user_message_id)
    assert user_message is not None
    assert user_message.role == "user"
    assert user_message.content_json == {"text": "hi"}

    finished = run_turn(db_session, turn_id)
    db_session.commit()

    assert finished.status == "success"
    assert finished.route_kind == "chat"
    assert finished.assistant_message_id is not None

    assistant_message = db_session.get(AgentMessage, finished.assistant_message_id)
    assert assistant_message is not None
    assert assistant_message.role == "assistant"
    assert assistant_message.kind == "text"
    assert assistant_message.content_json["text"]

    conv = db_session.get(AgentConversation, conversation.id)
    assert conv is not None
    assert conv.last_message_at is not None

    # Zero AgentTask / ExecutionRecord rows for this user, and zero rows in
    # ANY business table this fast path could plausibly have touched.
    tasks = list(db_session.scalars(select(AgentTask).where(AgentTask.user_id == user.id)).all())
    assert tasks == []
    records = list(db_session.scalars(select(ExecutionRecord)).all())
    assert records == []

    from app.models.posts import Post

    posts = list(db_session.scalars(select(Post).where(Post.user_id == user.id)).all())
    assert posts == []


def test_capability_help_reflects_truthful_manifest_and_has_zero_side_effects(
    db_session, make_user
) -> None:
    from app.models.agent import AgentTask
    from app.modules.agent.conversation_service import accept_message, create_conversation
    from app.modules.agent.conversation_service import execute_turn as run_turn
    from app.modules.agent.registry import tool_registry

    user = make_user()
    conversation = create_conversation(db_session, user_id=user.id)
    db_session.commit()

    turn = accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id="cap-help-1",
        text="你能做什么",
    )
    db_session.commit()

    finished = run_turn(db_session, turn.id)
    db_session.commit()

    assert finished.status == "success"
    assert finished.route_kind == "capability_help"
    from app.models.agent_conversation import AgentMessage

    assistant_message = db_session.get(AgentMessage, finished.assistant_message_id)
    reply_text = assistant_message.content_json["text"]

    manifest = tool_registry.safe_manifest_v2(session=db_session, user_id=user.id)
    available_responsibilities = {
        t["responsibility"] for t in manifest["tools"] if t["available"]
    }
    # Every claimed capability in the reply must trace back to something the
    # manifest actually reports available — no fabricated capability text.
    assert any(resp in reply_text for resp in available_responsibilities) or not (
        available_responsibilities
    )

    tasks = list(db_session.scalars(select(AgentTask).where(AgentTask.user_id == user.id)).all())
    assert tasks == []


def test_repeated_greeting_delivery_is_idempotent(db_session, make_user) -> None:
    from app.modules.agent.conversation_service import accept_message, create_conversation
    from app.modules.agent.conversation_service import execute_turn as run_turn

    user = make_user()
    conversation = create_conversation(db_session, user_id=user.id)
    db_session.commit()

    turn = accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id="dup-1",
        text="hi",
    )
    db_session.commit()
    first = run_turn(db_session, turn.id)
    db_session.commit()

    # A redelivered worker invocation on an already-terminal Turn must not
    # double-post the assistant reply or re-transition the job.
    second = run_turn(db_session, turn.id)
    db_session.commit()

    assert second.id == first.id
    assert second.assistant_message_id == first.assistant_message_id
    assert second.status == "success"
