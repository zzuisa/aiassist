"""Deterministic fast-path detection for pure conversation.

This module answers exactly one question: is a user message answerable
WITHOUT any task routing, tool call, or LLM call — i.e. is it a pure
greeting, thanks, goodbye, or a "what can you do" capability question? If
so it also builds the truthful reply text.

It deliberately does NOT do LLM-based routing, task recognition, or MCP
tool selection — that is ``conversation-route.v1`` territory, built on top
of this module in Phase 4 (US2). A message that mixes a greeting with a
task (e.g. "嗨，帮我看文章") must NOT be classified as fast-path here: the
whole-message match below only fires when the ENTIRE normalized message is
one of the known phrases, so any extra content correctly falls through.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.modules.agent.capability_selector import reduce_candidates, validate_route
from app.modules.agent.conversation_schemas import ConversationRoute, TargetScope
from app.modules.agent.registry import tool_registry
from app.services.llm.base import LLMError, StructuredRequest

# Punctuation/whitespace stripped from both ends before matching. Deliberately
# NOT stripped from the middle — "你 好" and "你好" are treated differently.
_STRIP_CHARS = " \t\r\n!?~。！？，,.·、…～-–—:：;；\"'“”‘’()（）"


def _normalize(text: str) -> str:
    return text.strip(_STRIP_CHARS).casefold()


GREETING_PHRASES = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "hiya",
        "yo",
        "morning",
        "good morning",
        "good afternoon",
        "good evening",
        "嗨",
        "你好",
        "您好",
        "你好呀",
        "你好啊",
        "哈喽",
        "哈啰",
        "早",
        "早安",
        "早上好",
        "中午好",
        "下午好",
        "晚上好",
        "在吗",
        "在么",
        "在不在",
    }
)

THANKS_PHRASES = frozenset(
    {
        "thanks",
        "thank you",
        "thanks a lot",
        "thx",
        "ty",
        "谢谢",
        "谢谢你",
        "谢谢啦",
        "谢谢了",
        "多谢",
        "感谢",
        "感谢你",
        "辛苦了",
    }
)

GOODBYE_PHRASES = frozenset(
    {
        "bye",
        "goodbye",
        "bye bye",
        "see you",
        "see you later",
        "再见",
        "拜拜",
        "晚安",
        "88",
    }
)

CAPABILITY_HELP_PHRASES = frozenset(
    {
        "你能做什么",
        "你能干什么",
        "你会做什么",
        "你都能做什么",
        "你有什么功能",
        "你有哪些功能",
        "你可以做什么",
        "介绍一下你自己",
        "你是谁",
        "what can you do",
        "what can you help with",
        "what can you help me with",
        "what do you do",
        "能做什么",
    }
)


class FastPathKind(StrEnum):
    greeting = "greeting"
    thanks = "thanks"
    goodbye = "goodbye"
    capability_help = "capability_help"


# Maps a fine-grained fast-path kind onto the persisted ``AgentTurn.route_kind``
# / ``conversation-route.v1`` ``route_kind`` enum, which only knows "chat" and
# "capability_help" (see data-model.md ROUTE_KINDS).
_ROUTE_KIND_FOR_FAST_PATH = {
    FastPathKind.greeting: "chat",
    FastPathKind.thanks: "chat",
    FastPathKind.goodbye: "chat",
    FastPathKind.capability_help: "capability_help",
}


def classify_fast_path(text: str) -> FastPathKind | None:
    """Return the fast-path kind for a message, or ``None`` if it is not pure
    conversation (including any mixed greeting+task message)."""
    normalized = _normalize(text)
    if not normalized:
        return None
    if normalized in CAPABILITY_HELP_PHRASES:
        return FastPathKind.capability_help
    if normalized in GREETING_PHRASES:
        return FastPathKind.greeting
    if normalized in THANKS_PHRASES:
        return FastPathKind.thanks
    if normalized in GOODBYE_PHRASES:
        return FastPathKind.goodbye
    return None


def route_kind_for(kind: FastPathKind) -> str:
    """Map a fast-path kind onto the persisted ``route_kind`` value."""
    return _ROUTE_KIND_FOR_FAST_PATH[kind]


_CHAT_REPLIES = {
    FastPathKind.greeting: "你好！我可以帮你查询、分析你的内容和日程；直接告诉我你想做什么就行。",
    FastPathKind.thanks: "不客气！还有什么想让我处理的，随时告诉我。",
    FastPathKind.goodbye: "好的，再见！有需要随时回来找我。",
}


def _capability_help_text(session: Session, user_id: uuid.UUID) -> str:
    """Build a truthful "what can you do" reply from the CURRENT safe manifest.

    Never a hardcoded capability list: reads ``ToolRegistry.safe_manifest_v2``
    so the reply cannot drift from what is actually available and authorized
    for this user.
    """
    manifest = tool_registry.safe_manifest_v2(session=session, user_id=user_id)
    tools = manifest.get("tools", [])
    available = [t for t in tools if t.get("available")]
    unavailable = [t for t in tools if not t.get("available")]

    if not available:
        base = "目前我还没有可用的能力（可能是未连接或未授权）。"
    else:
        summaries = "；".join(f"{t.get('responsibility', t.get('key', ''))}" for t in available[:8])
        base = f"我目前可以：{summaries}。"

    if unavailable:
        reasons = "；".join(
            f"{t.get('responsibility', t.get('key', ''))}"
            f"（{t.get('unavailable_reason') or '暂不可用'}）"
            for t in unavailable[:5]
        )
        base += f" 另外这些还不可用：{reasons}。"

    return base + " 直接用一句话告诉我你想做什么就可以了。"


def build_fast_path_reply(
    kind: FastPathKind,
    *,
    session: Session,
    user_id: uuid.UUID,
) -> str:
    """Build the truthful reply text for a fast-path kind. No side effects."""
    if kind is FastPathKind.capability_help:
        return _capability_help_text(session, user_id)
    return _CHAT_REPLIES[kind]


@dataclass(frozen=True, slots=True)
class RoutingOutcome:
    route: ConversationRoute
    selected_tool: str | None
    validation_errors: tuple[str, ...] = ()


def _clarification_route(question: str, *, objective: str = "补充任务信息") -> ConversationRoute:
    return ConversationRoute(
        route_kind="clarification",
        objective=objective,
        operation_type="none",
        target_scope=TargetScope(source="none", object_type=None, object_ids=[]),
        semantic_arguments={},
        candidate_tool_keys=[],
        clarification_question=question,
        requires_confirmation=False,
        confidence=1.0,
    )


def route_message(
    text: str,
    *,
    session: Session,
    user_id: uuid.UUID,
    context: Mapping[str, Any] | None = None,
    gateway: Any | None = None,
    run_reference: str | None = None,
) -> RoutingOutcome:
    """Generate and policy-check one structured conversation-route.v1 decision."""
    manifest = tool_registry.safe_manifest_v2(session=session, user_id=user_id)
    safe_context = {
        "object_type": (context or {}).get("object_type"),
        "object_ids": list((context or {}).get("object_ids", []))[:500],
        "query_conditions": dict((context or {}).get("query_conditions", {})),
        "pending_write_ids": list((context or {}).get("pending_write_ids", []))[:50],
    }
    candidates = reduce_candidates(
        manifest,
        text,
        scope_object_type=str(safe_context.get("object_type") or "") or None,
    )
    if not candidates:
        route = _clarification_route("我还不能确定应使用哪项已授权能力，请具体说明对象和期望结果。")
        return RoutingOutcome(route, None, ("no_candidates",))

    if gateway is None:
        from app.services.llm.gateway import get_llm_gateway

        gateway = get_llm_gateway()
    from app.modules.ai_config.service import bind

    config = bind(session, user_id, "conversation_route", run_reference=run_reference)
    prompt_payload = {
        "message": text,
        "conversation_context": safe_context,
        "candidate_tools": [item for item in manifest["tools"] if item.get("key") in candidates],
        "skill_tool_defaults": config.tool_defaults,
    }
    try:
        route = gateway.structured(
            StructuredRequest(
                scenario="conversation_route",
                system=config.system_instruction,
                user=json.dumps(prompt_payload, ensure_ascii=False),
                schema=ConversationRoute,
                temperature=0.0,
                max_tokens=1200,
                repair_attempts=1,
            )
        )
    except LLMError:
        route = _clarification_route("任务路由能力暂时不可用，请稍后重试；你的消息已经安全保存。")
        return RoutingOutcome(route, None, ("router_unavailable",))

    if route.tool_call is not None:
        defaults = config.tool_defaults.get(route.tool_call.name, {})
        arguments = {**defaults, **route.tool_call.arguments}
        try:
            tool_registry.get(route.tool_call.name).validate_arguments(arguments)
        except ValidationError:
            fallback = _clarification_route(
                "调用参数不符合该能力的要求，请换一种方式说明范围或数量。",
                objective=route.objective,
            )
            return RoutingOutcome(fallback, None, ("tool_arguments_invalid",))
        route = route.model_copy(
            update={
                "candidate_tool_keys": [route.tool_call.name],
                "semantic_arguments": arguments,
                "tool_call": route.tool_call.model_copy(update={"arguments": arguments}),
            }
        )

    policy = validate_route(route, manifest, allowed_candidates=candidates)
    if not policy.valid:
        fallback = _clarification_route(
            policy.clarification_question or "请补充完成任务所需的信息。",
            objective=route.objective,
        )
        return RoutingOutcome(fallback, None, policy.errors)
    return RoutingOutcome(route, policy.selected_tool, policy.errors)
