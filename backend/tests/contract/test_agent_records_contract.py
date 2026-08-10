"""REST contract for an owned Agent task's execution records."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = [pytest.mark.contract]


def _login(client, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_execution_records_contract(client, make_user, monkeypatch) -> None:
    from app.db.session import session_scope
    from app.models.agent import AgentTask
    from app.modules.agent.audit import write_execution_record

    user = make_user()
    headers = _login(client, user.email)
    monkeypatch.setattr("app.modules.agent.router.execute_task.delay", lambda _task_id: None)
    created = client.post(
        "/api/v1/agent/tasks",
        headers=headers,
        json={"request_text": "记录完整执行过程"},
    ).json()

    operation_types = ["query", "analyze", "create", "update", "delete", "publish", "rollback"]
    started = datetime.now(UTC)
    with session_scope() as session:
        task = session.get(AgentTask, uuid.UUID(created["task_id"]))
        assert task is not None
        for index, operation_type in enumerate(operation_types, start=1):
            write_execution_record(
                session,
                task_id=task.id,
                step_id=f"step-{index:04d}",
                agent_name="审计 Agent",
                step_label=f"步骤 {index}",
                tool_name="audit.contract",
                operation_type=operation_type,
                params={"index": index},
                status="success",
                started_at=started,
                finished_at=started + timedelta(milliseconds=index),
            )

    response = client.get(f"/api/v1/agent/tasks/{created['task_id']}/records")
    assert response.status_code == 200
    records = response.json()
    assert [item["operation_type"] for item in records] == operation_types
    assert [item["step_id"] for item in records] == [
        f"step-{index:04d}" for index in range(1, 8)
    ]
    assert set(records[0]) == {
        "step_id",
        "agent_id",
        "agent_name",
        "step_label",
        "tool_name",
        "operation_type",
        "params_digest",
        "result_summary",
        "status",
        "error_reason",
        "started_at",
        "finished_at",
        "duration_ms",
    }


def test_execution_records_require_task_ownership(client, make_user, monkeypatch) -> None:
    owner = make_user(email="records-owner@example.com")
    other = make_user(email="records-other@example.com")
    headers = _login(client, owner.email)
    monkeypatch.setattr("app.modules.agent.router.execute_task.delay", lambda _task_id: None)
    created = client.post(
        "/api/v1/agent/tasks",
        headers=headers,
        json={"request_text": "私有审计记录"},
    ).json()

    _login(client, other.email)
    response = client.get(f"/api/v1/agent/tasks/{created['task_id']}/records")
    assert response.status_code == 404
