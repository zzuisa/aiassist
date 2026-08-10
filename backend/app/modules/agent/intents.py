"""Extensible intent registry for Agent request dispatch."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, ParamSpec, TypeVar

from app.core.errors import ConflictError, ValidationError

P = ParamSpec("P")
R = TypeVar("R")
IntentHandler = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class IntentDefinition:
    key: str
    handler: IntentHandler


@dataclass(frozen=True, slots=True)
class IntentPlan:
    tool_name: str
    params: dict[str, Any]
    clarification_question: str | None = None
    execution_kind: Literal["query", "analysis", "capability_gap", "assistant_compat"] = "query"


@dataclass(frozen=True, slots=True)
class IntentRule:
    key: str
    signals: tuple[str, ...]


class IntentRegistry:
    """Maps stable intent keys to handlers without a central branch chain."""

    def __init__(self) -> None:
        self._definitions: dict[str, IntentDefinition] = {}

    def register(self, intent_key: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
        key = intent_key.strip()
        if not key or len(key) > 64:
            raise ValidationError(
                "Intent key must contain 1 to 64 characters",
                code="agent_intent_key_invalid",
            )

        def decorator(handler: Callable[P, R]) -> Callable[P, R]:
            if key in self._definitions:
                raise ConflictError(
                    f"Intent already registered: {key}",
                    code="agent_intent_duplicate",
                )
            self._definitions[key] = IntentDefinition(key=key, handler=handler)
            return handler

        return decorator

    def resolve(self, intent_key: str) -> IntentHandler:
        definition = self._definitions.get(intent_key)
        if definition is None:
            raise ValidationError(
                f"Unknown intent: {intent_key}",
                code="agent_intent_unknown",
            )
        return definition.handler

    def dispatch(self, intent_key: str, *args: Any, **kwargs: Any) -> Any:
        return self.resolve(intent_key)(*args, **kwargs)

    def keys(self) -> tuple[str, ...]:
        return tuple(self._definitions)


intent_registry = IntentRegistry()
register_intent = intent_registry.register
dispatch_intent = intent_registry.dispatch


def _recent_limit(request_text: str) -> int | None:
    for pattern in (r"最近\s*(\d+)\s*篇", r"(\d+)\s*篇"):
        match = re.search(pattern, request_text)
        if match:
            return min(max(int(match.group(1)), 1), 100)
    return None


@register_intent("articles.list_recent")
def plan_recent_articles(request_text: str) -> IntentPlan:
    limit = _recent_limit(request_text)
    if limit is None:
        return IntentPlan(
            tool_name="posts.list_recent",
            params={},
            clarification_question="需要查看最近多少篇文章？",
        )
    return IntentPlan(tool_name="posts.list_recent", params={"limit": limit})


@register_intent("taxonomy.categories")
def plan_category_statistics(_request_text: str) -> IntentPlan:
    return IntentPlan(tool_name="taxonomy.categories", params={})


@register_intent("taxonomy.tags")
def plan_tag_statistics(_request_text: str) -> IntentPlan:
    return IntentPlan(tool_name="taxonomy.tags", params={})


@register_intent("articles.analyze")
def plan_article_analysis(_request_text: str) -> IntentPlan:
    return IntentPlan(
        tool_name="content.extract_metadata",
        params={},
        execution_kind="analysis",
    )


@register_intent("capability.unknown")
def plan_capability_gap(_request_text: str) -> IntentPlan:
    return IntentPlan(
        tool_name="agent.capabilities",
        params={},
        execution_kind="capability_gap",
    )


@register_intent("plan_today")
@register_intent("adjust_week")
def plan_legacy_assistant(_request_text: str) -> IntentPlan:
    return IntentPlan(
        tool_name="assistant.plan_tasks",
        params={},
        execution_kind="assistant_compat",
    )


_CLASSIFICATION_RULES = (
    IntentRule("articles.analyze", ("提取标签", "关键词", "内容分析", "总结", "优化", "比较")),
    IntentRule("taxonomy.categories", ("类别", "分类")),
    IntentRule("taxonomy.tags", ("标签",)),
    IntentRule("articles.list_recent", ("文章", "博客")),
)


def classify_request(request_text: str) -> str:
    """Data-driven keyword classifier; dispatch remains registry-based."""
    normalized = request_text.casefold()
    for rule in _CLASSIFICATION_RULES:
        if any(signal in normalized for signal in rule.signals):
            return rule.key
    return "capability.unknown"
