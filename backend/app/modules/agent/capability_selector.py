"""Deterministic post-model routing policy.

The model never sees endpoints, credentials, grants, or server instructions. It
only receives the already-authorized entries emitted by safe-manifest v2. The
policy here validates the model's final decision; it never infers intent or
selects tools from user-message keywords.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.modules.agent.conversation_schemas import ConversationRoute


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
