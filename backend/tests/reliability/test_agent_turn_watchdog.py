from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytestmark = [pytest.mark.reliability]


def test_watchdog_stalls_only_expired_nonterminal_turn(db_session, make_user) -> None:
    from app.modules.agent.conversation_service import accept_message, create_conversation
    from app.modules.agent.watchdog import repair_stalled_turns

    user = make_user()
    conversation = create_conversation(db_session, user_id=user.id)
    turn = accept_message(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        client_message_id="stall-1",
        text="任务",
    )
    turn.status = "executing"
    turn.last_heartbeat_at = datetime.now(UTC) - timedelta(hours=1)
    assert repair_stalled_turns(db_session) == 1
    assert turn.status == "stalled"
    assert repair_stalled_turns(db_session) == 0
