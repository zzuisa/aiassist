"""Versioned planner applies Skill defaults and validates a compound DAG."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


def test_compound_planner_keeps_parallel_roots_and_dependency(db_session, make_user) -> None:
    from app.modules.agent.planning_schemas import AgentTaskPlanProposal
    from app.modules.agent.planning_service import propose_plan

    class Gateway:
        def structured(self, _request):
            return AgentTaskPlanProposal.model_validate(
                {
                    "objective": "查询并统计",
                    "steps": [
                        {
                            "step_key": "step_posts",
                            "title": "查询文章",
                            "responsibility": "取得文章范围",
                            "tool_name": "posts.list_recent",
                            "operation_type": "query",
                            "arguments": {},
                            "depends_on": [],
                            "input_source": "current_message",
                            "expected_output": "文章 ID",
                            "requires_confirmation": False,
                        },
                        {
                            "step_key": "step_tags",
                            "title": "统计标签",
                            "responsibility": "统计标签",
                            "tool_name": "taxonomy.tags",
                            "operation_type": "query",
                            "arguments": {},
                            "depends_on": [],
                            "input_source": "current_message",
                            "expected_output": "标签统计",
                            "requires_confirmation": False,
                        },
                        {
                            "step_key": "step_analyze",
                            "title": "分析文章",
                            "responsibility": "生成元数据提案",
                            "tool_name": "content.extract_metadata",
                            "operation_type": "analyze",
                            "arguments": {},
                            "depends_on": ["step_posts"],
                            "input_source": "dependency",
                            "expected_output": "文章分析提案",
                            "requires_confirmation": False,
                        },
                    ],
                }
            )

    user = make_user()
    proposal = propose_plan(
        db_session,
        user_id=user.id,
        request_text="查询最近文章，同时统计标签，然后分析文章",
        objective="查询并统计",
        seed_tool_name="posts.list_recent",
        seed_arguments={},
        context={},
        gateway=Gateway(),
    )
    by_key = {step.step_key: step for step in proposal.steps}
    assert by_key["step_posts"].arguments == {"limit": 10}
    assert by_key["step_tags"].depends_on == []
    assert by_key["step_analyze"].depends_on == ["step_posts"]
