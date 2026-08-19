"""REST ownership and public-shape contract for collaborative plans."""

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


def test_plan_endpoints_return_owned_safe_snapshot(client, make_user, monkeypatch) -> None:
    from app.db.session import session_scope
    from app.models.agent_conversation import AgentTurn
    from app.modules.agent.planning_schemas import AgentTaskPlanProposal
    from app.modules.agent.planning_service import persist_plan
    from app.modules.agent.service import create_agent_task

    monkeypatch.setattr("app.modules.agent.router.execute_conversation_turn.delay", lambda _: None)
    owner = make_user()
    headers = _login(client, owner.email)
    conversation_id = client.post("/api/v1/agent/conversations", headers=headers).json()["id"]
    accepted = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        headers=headers,
        json={"client_message_id": str(uuid.uuid4()), "text": "列出最近 2 篇文章"},
    ).json()

    with session_scope() as session:
        turn = session.get(AgentTurn, uuid.UUID(accepted["turn"]["id"]))
        assert turn is not None
        task = create_agent_task(
            session,
            user_id=owner.id,
            request_text="列出最近 2 篇文章",
            intent_key="articles.list_recent",
        )
        turn.agent_task_id = task.id
        proposal = AgentTaskPlanProposal.model_validate(
            {
                "objective": "查询文章",
                "steps": [
                    {
                        "step_key": "step_query",
                        "title": "查询文章",
                        "responsibility": "取得文章范围",
                        "tool_name": "posts.list_recent",
                        "operation_type": "query",
                        "arguments": {"limit": 2},
                        "depends_on": [],
                        "input_source": "current_message",
                        "expected_output": "文章 ID",
                        "requires_confirmation": False,
                    }
                ],
            }
        )
        plan_id = persist_plan(session, task=task, proposal=proposal, turn=turn).id

    response = client.get(f"/api/v1/agent/plans/{plan_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["plan_id"] == str(plan_id)
    assert payload["steps"][0]["tool_name"] == "posts.list_recent"
    serialized = response.text.casefold()
    assert "arguments_json" not in serialized
    assert "prompt" not in serialized

    other = make_user()
    _login(client, other.email)
    assert client.get(f"/api/v1/agent/plans/{plan_id}").status_code == 404
