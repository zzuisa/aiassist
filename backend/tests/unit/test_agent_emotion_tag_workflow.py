from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.unit]


def test_llm_decides_search_semantics_without_keyword_override(
    db_session, make_user, monkeypatch
) -> None:
    from app.modules.agent.conversation_router import route_message
    from app.modules.agent.conversation_schemas import ConversationRoute
    from app.modules.agent.registry import ToolDefinition, tool_registry

    search_tool = ToolDefinition(
        name="mcp.roguelife-blog.blog_search_posts",
        safe_name="roguelife-blog-blog_search_posts",
        source="mcp",
        type="read",
        responsibility="在博客标题和正文中搜索",
        handler=lambda _context, _params: {},
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "cursor": {"type": "integer", "minimum": 0},
            },
            "required": ["query"],
        },
    )
    manifest = {
        "tools": [
            {
                "key": "posts.list_recent",
                "available": True,
                "type": "read",
                "input_schema": {"type": "object", "properties": {"limit": {}}},
            },
            {
                "key": search_tool.safe_name,
                "available": True,
                "type": "read",
                "input_schema": search_tool.input_schema,
            },
        ]
    }
    monkeypatch.setattr(tool_registry, "safe_manifest_v2", lambda **_kwargs: manifest)
    monkeypatch.setattr(tool_registry, "get", lambda _key: search_tool)

    class Gateway:
        request = None

        def structured(self, request):
            self.request = request
            return ConversationRoute.model_validate(
                {
                    "route_kind": "task",
                    "objective": "搜索内容含有女人的最近 3 篇文章",
                    "operation_type": "query",
                    "target_scope": {
                        "source": "current_message",
                        "object_type": "post",
                        "object_ids": [],
                    },
                    "semantic_arguments": {},
                    "candidate_tool_keys": [search_tool.safe_name],
                    "tool_call": {
                        "name": search_tool.safe_name,
                        "arguments": {"query": "女人", "limit": 3, "cursor": 0},
                    },
                    "requires_confirmation": False,
                    "confidence": 0.96,
                }
            )

    gateway = Gateway()
    user = make_user()
    outcome = route_message(
        "查询最近3篇内容含有女人的文章",
        session=db_session,
        user_id=user.id,
        gateway=gateway,
    )

    assert outcome.selected_tool == search_tool.safe_name
    assert outcome.route.semantic_arguments == {"query": "女人", "limit": 3, "cursor": 0}
    assert gateway.request.reasoning_budget == 512
    prompt_tools = json.loads(gateway.request.user)["candidate_tools"]
    assert {tool["key"] for tool in prompt_tools} == {
        "posts.list_recent",
        search_tool.safe_name,
    }


def test_llm_planner_decides_tag_workflow(db_session, make_user) -> None:
    from app.modules.agent.planning_schemas import AgentTaskPlanProposal
    from app.modules.agent.planning_service import propose_plan, validate_plan_graph

    class Gateway:
        request = None

        def structured(self, request):
            self.request = request
            return AgentTaskPlanProposal.model_validate(
                {
                    "objective": "处理情感博客标签",
                    "steps": [
                        {
                            "step_key": "step_search",
                            "title": "搜索目标博客",
                            "responsibility": "查询用户指定数量的目标博客",
                            "tool_name": "posts.list_recent",
                            "operation_type": "query",
                            "arguments": {"limit": 8},
                            "depends_on": [],
                            "input_source": "current_message",
                            "expected_output": "返回目标博客及现有标签",
                            "requires_confirmation": False,
                        },
                        {
                            "step_key": "step_check_tags",
                            "title": "检查文章标签",
                            "responsibility": "只保留没有标签的文章",
                            "tool_name": "posts.filter_missing_tags",
                            "operation_type": "query",
                            "arguments": {},
                            "depends_on": ["step_search"],
                            "input_source": "dependency",
                            "expected_output": "无标签文章",
                            "requires_confirmation": False,
                        },
                        {
                            "step_key": "step_generate_tags",
                            "title": "生成标签建议",
                            "responsibility": "为无标签文章生成标签建议",
                            "tool_name": "content.extract_metadata",
                            "operation_type": "analyze",
                            "arguments": {},
                            "depends_on": ["step_check_tags"],
                            "input_source": "dependency",
                            "expected_output": "结构化标签建议",
                            "requires_confirmation": False,
                        },
                        {
                            "step_key": "step_apply_tags",
                            "title": "确认并写入标签",
                            "responsibility": "确认后写入标签",
                            "tool_name": "posts.apply_analysis",
                            "operation_type": "update",
                            "arguments": {"fields": ["tags"]},
                            "depends_on": ["step_generate_tags"],
                            "input_source": "dependency",
                            "expected_output": "标签写入预览",
                            "requires_confirmation": True,
                        },
                        {
                            "step_key": "step_verify_tags",
                            "title": "回读验证标签",
                            "responsibility": "核对标签存在",
                            "tool_name": "posts.verify_tags",
                            "operation_type": "query",
                            "arguments": {},
                            "depends_on": ["step_apply_tags"],
                            "input_source": "dependency",
                            "expected_output": "标签验证结果",
                            "requires_confirmation": False,
                        },
                    ],
                }
            )

    gateway = Gateway()
    user = make_user()
    proposal = propose_plan(
        db_session,
        user_id=user.id,
        request_text="查询8篇关于情感的博客，如果没有标签则生成标签",
        objective="处理情感博客标签",
        seed_tool_name="posts.list_recent",
        seed_arguments={"limit": 8},
        context={},
        gateway=gateway,
    )

    assert gateway.request.reasoning_budget == 1024
    assert [step.step_key for step in proposal.steps] == [
        "step_search",
        "step_check_tags",
        "step_generate_tags",
        "step_apply_tags",
        "step_verify_tags",
    ]
    assert proposal.steps[0].arguments == {"limit": 8}
    assert proposal.steps[3].arguments == {"fields": ["tags"]}
    assert proposal.steps[3].requires_confirmation is True
    validate_plan_graph(proposal, max_depth=5)
