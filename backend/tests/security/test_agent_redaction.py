"""Agent execution records redact credentials before persistence."""

from __future__ import annotations

import json

import pytest
from app.models.agent import AgentRun
from app.modules.agent.audit import write_execution_record
from app.modules.agent.service import create_agent_task

pytestmark = [pytest.mark.security]


def test_execution_record_is_persisted_without_credentials(db_session, make_user) -> None:
    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="安全审计测试",
        intent_key="test.audit",
    )
    run = AgentRun(
        task_id=task.id,
        agent_key="test-agent",
        agent_version="v1",
        agent_name="测试 Agent",
        responsibility="验证审计脱敏",
        current_task="写入执行记录",
        status="running",
    )
    db_session.add(run)
    db_session.flush()

    secrets = {
        "password": "password-value",
        "access-token": "token-value",
        "nested": {
            "API_KEY": "api-key-value",
            "cookie": "cookie-value",
            "authorization": "Basic auth-value",
            "private-key": "private-key-value",
            "ordinary_jwt": "eyJhbGciOiJIUzI1NiJ9.payload.signature",
        },
        "items": [{"client_secret": "secret-value"}, "Bearer bearer-value"],
    }
    record = write_execution_record(
        db_session,
        task_id=task.id,
        run_id=run.id,
        step_id="step-1",
        agent_name=run.agent_name,
        step_label="调用测试工具",
        tool_name="test.tool",
        operation_type="query",
        params=secrets,
        status="success",
        result_summary="1 item",
    )
    db_session.commit()
    db_session.refresh(record)

    rendered = json.dumps(record.params_digest_json, ensure_ascii=False)
    for secret in (
        "password-value",
        "token-value",
        "api-key-value",
        "cookie-value",
        "auth-value",
        "private-key-value",
        "eyJhbGciOiJIUzI1NiJ9.payload.signature",
        "secret-value",
        "bearer-value",
    ):
        assert secret not in rendered
    assert rendered.count("[redacted]") >= 8
