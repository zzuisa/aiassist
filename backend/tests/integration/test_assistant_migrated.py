"""Legacy planning intents are ordinary registered Agent intents."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytestmark = [pytest.mark.integration]


def test_planning_intents_are_registered_and_fixed_events_have_no_actions(
    db_session,
    make_user,
) -> None:
    from app.modules.agent.intents import intent_registry
    from app.modules.assistant import service as assistant_service
    from app.modules.tasks import service as task_service
    from app.modules.tasks.schemas import TaskCreate

    registered = set(intent_registry.keys())
    assert "plan_today" in registered
    assert "adjust_week" in registered

    user = make_user()
    flexible = task_service.create_task(
        db_session,
        user.id,
        TaskCreate(title="可调整任务", type="task"),
    )
    fixed = task_service.create_task(
        db_session,
        user.id,
        TaskCreate(title="固定事项", type="fixed_event", is_fixed=True),
    )
    fixed.start_at = datetime.now(UTC) + timedelta(hours=2)
    db_session.flush()

    run = assistant_service.create_run(db_session, user.id, "adjust_week", None)
    actions = [action for card in run["cards"] for action in card["actions"]]

    assert any(action["id"] == f"reschedule:{flexible.id}" for action in actions)
    assert all(str(fixed.id) not in action["id"] for action in actions)
    assert {ref["id"] for ref in run["grounded_refs"]} >= {str(flexible.id), str(fixed.id)}
