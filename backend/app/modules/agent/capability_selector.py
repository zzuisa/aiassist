"""Deterministic candidate reduction and post-model routing policy.

The model never sees endpoints, credentials, grants, or server instructions. It
only receives the already-authorized entries emitted by safe-manifest v2. The
functions here are deliberately pure so authorization and route validation are
repeatable and easy to audit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.modules.agent.conversation_schemas import ConversationRoute

_WRITE_SIGNALS = (
    "保存",
    "写回",
    "更新",
    "修改",
    "删除",
    "发布",
    "创建",
    "确认后",
    "save",
    "apply",
    "persist",
    "update",
    "delete",
    "publish",
    "create",
)
_ANALYZE_SIGNALS = (
    "分析",
    "提取",
    "标签",
    "关键词",
    "摘要",
    "总结",
    "比较",
    "结构",
    "元数据",
    "优化",
    "analyze",
    "extract",
    "tag",
    "keyword",
    "summary",
    "compare",
    "metadata",
)
_QUERY_SIGNALS = (
    "最近",
    "最新",
    "列",
    "找",
    "查",
    "看看",
    "什么",
    "文章",
    "博客",
    "recent",
    "latest",
    "list",
    "show",
    "find",
    "query",
    "post",
    "article",
)
_SEMANTIC_SEARCH_SIGNALS = ("关于", "有关", "搜索", "查找", "包含", "search", "about")


def infer_operation_type(text: str) -> str:
    normalized = text.casefold()
    if any(signal in normalized for signal in _WRITE_SIGNALS):
        return "update"
    if any(signal in normalized for signal in _ANALYZE_SIGNALS):
        return "analyze"
    return "query"


def _safe_tools(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = manifest.get("tools", [])
    return [item for item in raw if isinstance(item, Mapping) and item.get("available") is True]


def reduce_candidates(
    manifest: Mapping[str, Any],
    text: str,
    *,
    operation_type: str | None = None,
    scope_object_type: str | None = None,
    max_candidates: int = 12,
) -> list[str]:
    """Return unique, available tool keys ordered by deterministic relevance."""
    operation = operation_type or infer_operation_type(text)
    normalized = text.casefold()
    scored: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for position, tool in enumerate(_safe_tools(manifest)):
        key = str(tool.get("key") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        tool_type = str(tool.get("type") or "")
        responsibility = str(tool.get("responsibility") or "").casefold()
        haystack = f"{key.casefold()} {responsibility}"
        input_schema = tool.get("input_schema")
        properties = input_schema.get("properties", {}) if isinstance(input_schema, Mapping) else {}
        score = 0
        if operation in {"create", "update", "delete", "publish", "rollback", "external_effect"}:
            score += 8 if tool_type == "write" else 1
        else:
            score += 5 if tool_type == "read" else -4
        if any(signal in normalized for signal in _ANALYZE_SIGNALS):
            if key == "content.extract_metadata":
                score += 20
            if key == "posts.apply_analysis" and operation == "update":
                score += 24
        if any(signal in normalized for signal in _QUERY_SIGNALS) and key == "posts.list_recent":
            score += 18
        if any(signal in normalized for signal in _SEMANTIC_SEARCH_SIGNALS):
            if isinstance(properties, Mapping) and any(
                field in properties for field in ("query", "search")
            ):
                score += 28
            if key == "posts.list_recent":
                score -= 16
        if "标签" in normalized and operation == "query" and key == "taxonomy.tags":
            score += 16
        for token in set(normalized.replace("，", " ").replace(",", " ").split()):
            if len(token) >= 2 and token in haystack:
                score += 2
        if scope_object_type and scope_object_type.casefold() in haystack:
            score += 2
        if score > 0:
            scored.append((score, -position, key))
    scored.sort(reverse=True)
    return [key for _, _, key in scored[: max(1, min(max_candidates, 12))]]


@dataclass(frozen=True, slots=True)
class RoutePolicyResult:
    valid: bool
    selected_tool: str | None
    errors: tuple[str, ...]
    clarification_question: str | None = None


def validate_route(
    route: ConversationRoute,
    manifest: Mapping[str, Any],
    *,
    allowed_candidates: list[str],
    confidence_threshold: float = 0.65,
) -> RoutePolicyResult:
    """Apply deterministic availability/type/confirmation policy after the model."""
    if route.route_kind != "task":
        if route.route_kind == "clarification":
            question = route.clarification_question or "请补充完成请求所需的对象或范围。"
            return RoutePolicyResult(True, None, (), question)
        return RoutePolicyResult(True, None, ())

    errors: list[str] = []
    proposed = list(route.candidate_tool_keys)
    if route.tool_call is not None:
        if proposed and proposed[0] != route.tool_call.name:
            errors.append("tool_call_candidate_mismatch")
        proposed = [route.tool_call.name]
    if not proposed or any(key not in allowed_candidates for key in proposed):
        errors.append("candidate_not_allowed")
    selected = proposed[0] if proposed else None
    entries = {
        str(item.get("key")): item
        for item in manifest.get("tools", [])
        if isinstance(item, Mapping) and item.get("key")
    }
    tool = entries.get(selected or "")
    if tool is None or tool.get("available") is not True:
        errors.append("tool_unavailable")
    if tool is not None:
        expected = (
            "write"
            if route.operation_type
            in {"create", "update", "delete", "publish", "rollback", "external_effect"}
            else "read"
        )
        if tool.get("type") != expected:
            errors.append("operation_type_mismatch")
        if expected == "write" and not route.requires_confirmation:
            errors.append("confirmation_required")
    if route.confidence < confidence_threshold:
        errors.append("confidence_too_low")
    if errors:
        return RoutePolicyResult(
            False,
            None,
            tuple(dict.fromkeys(errors)),
            route.clarification_question
            or "我还不能安全确定要使用的能力，请补充对象、范围和期望操作。",
        )
    return RoutePolicyResult(True, selected, ())
