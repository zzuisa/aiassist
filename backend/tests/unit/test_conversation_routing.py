"""Natural-language variants produce bounded safe capability candidates."""

from __future__ import annotations

import pytest
from app.modules.agent.capability_selector import infer_operation_type, reduce_candidates

pytestmark = [pytest.mark.unit]

MANIFEST = {
    "schema_version": "safe-tool-manifest.v2",
    "tools": [
        {"key": "posts.list_recent", "source": "internal_api", "type": "read", "responsibility": "按时间返回最近文章和博客", "input_schema": {"type": "object"}, "risk": {}, "required_permission": "posts:read", "available": True, "unavailable_reason": None},
        {"key": "content.extract_metadata", "source": "internal_api", "type": "read", "responsibility": "分析文章并提取标签关键词摘要", "input_schema": {"type": "object"}, "risk": {}, "required_permission": "posts:read", "available": True, "unavailable_reason": None},
        {"key": "posts.apply_analysis", "source": "internal_api", "type": "write", "responsibility": "保存文章分析结果", "input_schema": {"type": "object"}, "risk": {"requires_confirmation": True}, "required_permission": "posts:write", "available": True, "unavailable_reason": None},
        {"key": "taxonomy.tags", "source": "internal_api", "type": "read", "responsibility": "统计文章标签", "input_schema": {"type": "object"}, "risk": {}, "required_permission": "posts:read", "available": True, "unavailable_reason": None},
    ],
}


@pytest.mark.parametrize(
    "text",
    [
        "最近十篇文章", "帮我找最近 10 篇文章", "列一下最近的博客", "show my 10 latest posts",
        "list recent articles", "嗨，帮我看看最近写的内容", "我最近写了什么", "取回最新文章",
    ],
)
def test_query_variants_include_recent_posts(text: str) -> None:
    assert "posts.list_recent" in reduce_candidates(MANIFEST, text)
    assert infer_operation_type(text) == "query"


@pytest.mark.parametrize(
    "text",
    [
        "提取这些文章的标签", "分析刚才的文章", "给文章生成关键词", "总结这几篇博客",
        "extract tags from those posts", "analyze the previous articles", "suggest keywords", "生成文章摘要",
        "比较刚才几篇文章", "帮我整理文章元数据", "看看内容结构", "做一次内容分析",
    ],
)
def test_analysis_variants_include_analysis_tool(text: str) -> None:
    assert "content.extract_metadata" in reduce_candidates(MANIFEST, text)
    assert infer_operation_type(text) == "analyze"


@pytest.mark.parametrize(
    "text",
    [
        "把标签保存", "保存刚才的分析", "更新文章摘要", "apply those tags", "save the generated keywords",
        "写回这些结果", "将摘要更新到文章", "确认后保存", "嗨，把刚才那些提取标签并保存", "persist the analysis",
    ],
)
def test_write_variants_include_write_and_analysis_tools(text: str) -> None:
    candidates = reduce_candidates(MANIFEST, text)
    assert "posts.apply_analysis" in candidates
    assert "content.extract_metadata" in candidates
    assert infer_operation_type(text) == "update"


def test_candidates_are_available_unique_and_bounded() -> None:
    manifest = {**MANIFEST, "tools": MANIFEST["tools"] * 8}
    candidates = reduce_candidates(manifest, "分析文章并保存", max_candidates=3)
    assert len(candidates) <= 3
    assert len(candidates) == len(set(candidates))

