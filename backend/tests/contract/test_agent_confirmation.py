"""REST contract for listing and deciding Agent write confirmations."""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.contract]


def _login(client, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_confirmation_list_and_reject_contract(client, make_user, monkeypatch) -> None:
    from app.db.session import session_scope
    from app.models.agent import AgentRun, AgentTask
    from app.modules.agent.service import create_pending_write

    user = make_user()
    headers = _login(client, user.email)
    monkeypatch.setattr("app.modules.agent.router.execute_task.delay", lambda _task_id: None)
    created = client.post(
        "/api/v1/agent/tasks",
        headers=headers,
        json={"request_text": "提取标签并保存"},
    ).json()

    with session_scope() as session:
        task = session.get(AgentTask, uuid.UUID(created["task_id"]))
        run = AgentRun(
            task_id=task.id,
            agent_key="editor-agent",
            agent_version="test-v1",
            agent_name="编辑 Agent",
            responsibility="生成并保存内容元数据",
            current_task=task.request_text,
            allowed_tools=["posts.apply_analysis"],
            status="running",
        )
        session.add(run)
        session.flush()
        pending = create_pending_write(
            session,
            task=task,
            run=run,
            operation_type="update",
            target_type="post",
            targets=[{"id": str(uuid.uuid4()), "version": 1}],
            preview={"summary": "写入标签", "changes": []},
            reversible=True,
            tool_name="posts.apply_analysis",
        )
        confirmation_id = str(pending.id)

    listed = client.get(f"/api/v1/agent/tasks/{created['task_id']}/confirmations")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert set(body[0]) == {
        "confirmation_id",
        "operation_type",
        "target_type",
        "targets",
        "preview",
        "affected_count",
        "reversible",
        "high_risk",
        "decision",
        "decided_at",
        "created_at",
    }
    assert body[0]["confirmation_id"] == confirmation_id
    assert body[0]["decision"] == "pending"

    decided = client.post(
        f"/api/v1/agent/tasks/{created['task_id']}/confirmations/{confirmation_id}",
        headers=headers,
        json={"decision": "reject"},
    )
    assert decided.status_code == 200
    assert decided.json()["decision"] == "rejected"
    assert decided.json()["decided_at"] is not None

    repeated = client.post(
        f"/api/v1/agent/tasks/{created['task_id']}/confirmations/{confirmation_id}",
        headers=headers,
        json={"decision": "approve"},
    )
    assert repeated.status_code == 409
