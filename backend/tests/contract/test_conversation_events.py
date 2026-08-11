from __future__ import annotations

import pytest

pytestmark = [pytest.mark.contract]


def test_conversation_events_are_bounded_and_replayable(db_session, make_user) -> None:
    from app.modules.agent.conversation_service import accept_message, create_conversation
    from app.modules.agent.status import (
        build_conversation_event_payload,
        publish_conversation_event,
    )

    user = make_user()
    conversation = create_conversation(db_session, user_id=user.id)
    turn = accept_message(db_session, user_id=user.id, conversation_id=conversation.id, client_message_id="event-1", text="hi")
    payload = build_conversation_event_payload(turn, event_type="conversation.turn_updated", result_summary="x" * 2000, error_message="y" * 2000)
    assert len(payload["result_summary"]) == 1000
    assert len(payload["error_message"]) == 1000
    event = publish_conversation_event(db_session, turn, event_type="conversation.turn_updated")
    assert event.user_id == user.id
    assert event.event_type == "conversation.turn_updated"

