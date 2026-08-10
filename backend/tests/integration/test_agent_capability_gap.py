"""Unsupported requests produce a structured capability gap."""

from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.integration]


def test_unknown_request_returns_complete_capability_gap(db_session, make_user) -> None:
    from app.modules.agent.service import create_agent_task, execute_agent_task

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="把我的数据同步到一台未配置的外部 CRM",
        intent_key="capability.unknown",
    )
    db_session.commit()

    completed = execute_agent_task(db_session, task.id)
    db_session.commit()
    reply = json.loads(completed.result_summary or "{}")
    gap = reply["能力缺口"]

    assert set(gap) == {
        "缺失能力",
        "缺失接口/字段/权限",
        "可完成部分",
        "不可完成部分",
        "建议补充项",
    }
    assert all(isinstance(gap[key], list) for key in gap)
    assert gap["缺失能力"]
    assert gap["不可完成部分"]
    assert completed.status == "partial_success"
