"""Today aggregation, current-task ranking, and AI/broker-independent durability."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.db.session import session_scope
from app.modules.tasks import service as task_service
from app.modules.tasks.schemas import TaskCreate

pytestmark = [pytest.mark.integration]


def test_current_task_prefers_in_progress_then_overdue(make_user):
    user = make_user()
    now = datetime.now(UTC)
    with session_scope() as s:
        task_service.create_task(s, user.id, TaskCreate(title="low", type="task", importance=0))
        overdue = task_service.create_task(
            s, user.id, TaskCreate(title="overdue", type="task", importance=1)
        )
        overdue.due_at = now - timedelta(hours=2)
        inprog = task_service.create_task(s, user.id, TaskCreate(title="doing", type="task"))
        inprog.status = "in_progress"
        uid = user.id

    with session_scope() as s:
        current = task_service.select_current_task(s, uid, now)
        assert current is not None
        assert current.title == "doing"


def test_current_task_none_when_no_open_tasks(make_user):
    user = make_user()
    with session_scope() as s:
        assert task_service.select_current_task(s, user.id) is None


def test_create_writes_outbox_and_activity_atomically(make_user):
    """Durable acceptance: task + activity + outbox committed in one transaction,
    with no dependency on a broker or worker being available."""
    from app.models.foundation import ActivityLog, OutboxEvent
    from app.models.tasks import Task
    from sqlalchemy import func, select

    user = make_user()
    with session_scope() as s:
        task_service.create_task(s, user.id, TaskCreate(title="reliable", type="task"))
        uid = user.id

    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(Task).where(Task.user_id == uid)) == 1
        assert (
            s.scalar(
                select(func.count()).select_from(ActivityLog).where(ActivityLog.user_id == uid)
            )
            >= 1
        )
        outbox = s.scalars(select(OutboxEvent).where(OutboxEvent.user_id == uid)).all()
        assert len(outbox) == 1
        # The event is pending — durable acceptance does NOT require it be published.
        assert outbox[0].status == "pending"


def test_today_endpoint_aggregates_open_tasks(client, make_user):
    from app.modules.auth import service as auth_service

    auth_service.reset_login_throttle()
    user = make_user()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    csrf = login.json()["csrf_token"]
    client.post(
        "/api/v1/tasks",
        json={"title": "今天要做", "type": "task"},
        headers={"X-CSRF-Token": csrf},
    )
    resp = client.get("/api/v1/today")
    assert resp.status_code == 200
    body = resp.json()
    assert "current_task" in body
    assert body["stats"]["open_count"] == 1
    assert isinstance(body["jobs"], list)


def test_today_is_user_isolated(client, make_user):
    from app.modules.auth import service as auth_service

    owner = make_user()
    other = make_user()
    auth_service.reset_login_throttle()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": owner.email, "password": "correct horse battery staple"},
    )
    csrf = login.json()["csrf_token"]
    client.post(
        "/api/v1/tasks",
        json={"title": "owner task", "type": "task"},
        headers={"X-CSRF-Token": csrf},
    )
    auth_service.reset_login_throttle()
    client.post(
        "/api/v1/auth/login",
        json={"email": other.email, "password": "correct horse battery staple"},
    )
    resp = client.get("/api/v1/today")
    assert resp.json()["stats"]["open_count"] == 0


# Silence unused import warnings in some runners
_ = uuid
