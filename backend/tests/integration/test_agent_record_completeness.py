"""Execution records preserve complete, ordered multi-step history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytestmark = [pytest.mark.integration]


def test_multi_step_records_are_complete_ordered_and_timed(db_session, make_user) -> None:
    from app.modules.agent.audit import list_execution_records, write_execution_record
    from app.modules.agent.service import create_agent_task

    user = make_user()
    task = create_agent_task(
        db_session,
        user_id=user.id,
        request_text="执行三个可审计步骤",
        intent_key="test.records",
    )
    started = datetime.now(UTC)
    expected = [
        ("success", None, 125),
        ("failed", "上游服务不可用", 250),
        ("skipped", "前置步骤失败", 0),
    ]
    written = []
    for index, (status, reason, duration_ms) in enumerate(expected, start=1):
        written.append(
            write_execution_record(
                db_session,
                task_id=task.id,
                step_id=None,
                agent_name="执行 Agent",
                step_label=f"执行步骤 {index}",
                tool_name=f"test.tool.{index}",
                operation_type="query",
                params={"step": index},
                status=status,
                error_reason=reason,
                started_at=started,
                finished_at=started + timedelta(milliseconds=duration_ms),
            )
        )
    db_session.commit()

    records = list_execution_records(db_session, task.id)

    assert [record.id for record in records] == [record.id for record in written]
    assert [record.step_id for record in records] == ["step-0001", "step-0002", "step-0003"]
    assert [record.status for record in records] == [item[0] for item in expected]
    assert [record.error_reason for record in records] == [item[1] for item in expected]
    assert [record.duration_ms for record in records] == [item[2] for item in expected]
    assert len({record.id for record in records}) == len(expected)
