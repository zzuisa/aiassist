"""Assistant: grounded refs, no-result honesty, fixed-event, selected-only effect."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.db.session import session_scope
from app.modules.assistant import service as assistant_service
from app.modules.tasks import service as task_service
from app.modules.tasks.schemas import TaskCreate

pytestmark = [pytest.mark.integration]


@pytest.fixture(autouse=True)
def _reset():
    assistant_service.clear_runs()
    yield
    assistant_service.clear_runs()


def test_no_result_is_honest(make_user):
    user = make_user()
    with session_scope() as s:
        run = assistant_service.create_run(s, user.id, "plan_today", None)
    assert run["cards"][0]["id"] == "no_result"
    assert run["grounded_refs"] == []


def test_plan_references_real_tasks_and_keeps_fixed(make_user):
    user = make_user()
    with session_scope() as s:
        task_service.create_task(s, user.id, TaskCreate(title="灵活任务", type="task"))
        fixed = task_service.create_task(
            s, user.id, TaskCreate(title="牙医", type="fixed_event", is_fixed=True)
        )
        fixed.start_at = datetime.now(UTC) + timedelta(hours=2)
        uid = user.id

    with session_scope() as s:
        run = assistant_service.create_run(s, uid, "plan_today", None)

    # Grounded refs reference actual tasks; the plan keeps fixed events.
    assert run["grounded_refs"]
    plan_card = next(c for c in run["cards"] if c["id"] == "plan")
    # No action targets the fixed event.
    action_labels = " ".join(a["label"] for a in plan_card["actions"])
    assert "牙医" not in action_labels
    assert str(fixed.id) in plan_card["body"]["fixed_kept"]


def test_apply_only_selected_action(make_user):
    user = make_user()
    with session_scope() as s:
        t1 = task_service.create_task(s, user.id, TaskCreate(title="任务一", type="task"))
        task_service.create_task(s, user.id, TaskCreate(title="任务二", type="task"))
        uid = user.id
        t1_id = t1.id

    with session_scope() as s:
        run = assistant_service.create_run(s, uid, "plan_today", None)
    run_id = run["id"]
    action_id = f"reschedule:{t1_id}"

    with session_scope() as s:
        result = assistant_service.execute_action(s, uid, run_id, action_id)
        assert result["applied"] == action_id

    with session_scope() as s:
        from app.models.tasks import Task

        t1_after = s.get(Task, t1_id)
        assert t1_after.start_at is not None  # selected task moved
        # The other task was untouched (still no start).
        others = [t for t in s.query(Task).filter_by(user_id=uid).all() if t.id != t1_id]
        assert all(o.start_at is None for o in others)


def test_fixed_event_action_rejected(make_user):
    """Even if a stale action referenced a fixed task, apply re-checks and rejects."""
    from app.core.errors import ConflictError

    user = make_user()
    with session_scope() as s:
        task = task_service.create_task(s, user.id, TaskCreate(title="灵活", type="task"))
        uid = user.id
        tid = task.id

    with session_scope() as s:
        run = assistant_service.create_run(s, uid, "plan_today", None)
    run_id = run["id"]

    # Make the task fixed after the run was generated.
    with session_scope() as s:
        from app.models.tasks import Task

        t = s.get(Task, tid)
        t.is_fixed = True
        t.is_ai_adjustable = False
        t.version += 1

    with session_scope() as s, pytest.raises(ConflictError):
        assistant_service.execute_action(s, uid, run_id, f"reschedule:{tid}")


def test_cross_user_run_not_accessible(make_user):
    from app.core.errors import NotFoundError

    owner = make_user()
    other = make_user()
    with session_scope() as s:
        task_service.create_task(s, owner.id, TaskCreate(title="t", type="task"))
        run = assistant_service.create_run(s, owner.id, "plan_today", None)
    with pytest.raises(NotFoundError):
        assistant_service.get_run(other.id, run["id"])
