from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


def test_emotion_blog_request_preserves_topic_and_exact_limit() -> None:
    from app.modules.agent.conversation_router import _requested_limit, _semantic_topic

    request = "帮我查询8篇关于情感的博客，并且查看是否都有标签，如果没有则生成标签"

    assert _semantic_topic(request) == "情感"
    assert _requested_limit(request) == 8


def test_reviewed_workflow_only_writes_tags() -> None:
    from app.modules.agent.planning_service import _missing_tag_workflow
    from app.modules.agent.registry import ToolDefinition

    search_tool = ToolDefinition(
        name="mcp.roguelife-blog.blog_search_posts",
        safe_name="roguelife-blog-blog_search_posts",
        source="mcp",
        type="read",
        responsibility="搜索博客",
        handler=lambda _context, _params: {},
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "cursor": {"type": "integer"},
            },
            "required": ["query"],
        },
    )

    proposal = _missing_tag_workflow(
        objective="处理情感博客标签",
        request_text="查询8篇关于情感的博客，如果没有标签则生成标签",
        search_tool_name="roguelife-blog-blog_search_posts",
        search_arguments={"query": "情感", "limit": 8, "cursor": 0},
        search_tool=search_tool,
    )

    assert proposal is not None
    assert [step.step_key for step in proposal.steps] == [
        "step_search",
        "step_check_tags",
        "step_generate_tags",
        "step_apply_tags",
        "step_verify_tags",
    ]
    assert proposal.steps[0].arguments == {"query": "情感", "limit": 8, "cursor": 0}
    assert proposal.steps[3].arguments == {"fields": ["tags"]}
    assert proposal.steps[3].requires_confirmation is True
