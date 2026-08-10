"""Typed registry for internal and MCP-backed Agent tools."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DependencyDegradedError, ValidationError

ToolType = Literal["read", "write"]
ToolSource = Literal["internal_api", "mcp"]


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Ownership and audit correlation passed to every tool invocation."""

    user_id: uuid.UUID
    task_id: uuid.UUID
    session: Session
    run_id: uuid.UUID | None = None


ToolHandler = Callable[[ToolContext, Mapping[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    type: ToolType
    responsibility: str
    handler: ToolHandler
    required_permission: str | None = None
    available: bool = True
    unavailable_reason: str | None = None
    source: ToolSource = "internal_api"
    timeout_seconds: float = 30.0
    max_retries: int = 1

    def safe_manifest(self) -> dict[str, str | bool | None]:
        """Return only fields allowed by agent-tool-manifest.v1."""
        return {
            "name": self.name,
            "type": self.type,
            "responsibility": self.responsibility,
            "required_permission": self.required_permission,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "source": self.source,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> ToolDefinition:
        if not definition.name or len(definition.name) > 120:
            raise ValidationError("Invalid tool name", code="agent_tool_name_invalid")
        if definition.name in self._tools:
            raise ConflictError(
                f"Tool already registered: {definition.name}",
                code="agent_tool_duplicate",
            )
        if definition.timeout_seconds <= 0 or definition.max_retries not in (0, 1):
            raise ValidationError(
                "Tool timeout must be positive and retries must be bounded to at most one",
                code="agent_tool_policy_invalid",
            )
        self._tools[definition.name] = definition
        return definition

    def get(self, name: str) -> ToolDefinition:
        tool = self._tools.get(name)
        if tool is None:
            raise ValidationError(
                f"Tool is not registered: {name}",
                code="agent_tool_unknown",
            )
        return tool

    def invoke(
        self,
        name: str,
        *,
        context: ToolContext,
        params: Mapping[str, Any],
    ) -> Any:
        tool = self.get(name)
        if not tool.available:
            raise DependencyDegradedError(
                tool.unavailable_reason or f"Tool is unavailable: {name}",
                code="agent_tool_unavailable",
            )
        if tool.type == "write":
            from app.models.agent import AgentRun, PendingWrite

            if context.run_id is None:
                raise ConflictError(
                    "Write tool requires an approved Agent run",
                    code="agent_write_approval_required",
                )
            run = context.session.get(AgentRun, context.run_id)
            if (
                run is None
                or run.task_id != context.task_id
                or not run.allow_write
                or name not in run.allowed_tools
            ):
                raise ConflictError(
                    "Write tool requires explicit approval",
                    code="agent_write_approval_required",
                )
            try:
                confirmation_id = uuid.UUID(str(params.get("confirmation_id") or ""))
            except ValueError as exc:
                raise ConflictError(
                    "Write tool requires an approved confirmation",
                    code="agent_write_approval_required",
                ) from exc
            pending = context.session.get(PendingWrite, confirmation_id)
            if (
                pending is None
                or pending.task_id != context.task_id
                or pending.run_id != context.run_id
                or pending.decision != "approved"
            ):
                raise ConflictError(
                    "Write tool requires an approved confirmation",
                    code="agent_write_approval_required",
                )
        return tool.handler(context, params)

    def safe_manifest(self) -> list[dict[str, str | bool | None]]:
        return [tool.safe_manifest() for tool in self._tools.values()]


tool_registry = ToolRegistry()


def check_agent_availability(
    agent_key: str,
    *,
    required_tools: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Resolve the spec-006 Agent and all required runtime tools without fallback."""
    from app.core.errors import NotFoundError
    from app.modules.posts.agent_manifest import resolve_builtin_agent

    try:
        binding = resolve_builtin_agent(agent_key)
    except NotFoundError:
        return {
            "agent_key": agent_key,
            "available": False,
            "unavailable_reason": "Agent 未在 spec 006 清单中注册",
            "version_ref": None,
        }
    if not binding.enabled:
        return {
            "agent_key": agent_key,
            "available": False,
            "unavailable_reason": "Agent 已在 spec 006 中停用",
            "version_ref": binding.version_ref,
        }
    for tool_name in required_tools:
        try:
            tool = tool_registry.get(tool_name)
        except ValidationError:
            return {
                "agent_key": agent_key,
                "available": False,
                "unavailable_reason": f"所需工具 {tool_name} 未注册",
                "version_ref": binding.version_ref,
            }
        if not tool.available:
            return {
                "agent_key": agent_key,
                "available": False,
                "unavailable_reason": tool.unavailable_reason or f"所需工具 {tool_name} 不可用",
                "version_ref": binding.version_ref,
            }
    return {
        "agent_key": agent_key,
        "available": True,
        "unavailable_reason": None,
        "version_ref": binding.version_ref,
    }


def _inspect_agent_capability(
    _context: ToolContext,
    params: Mapping[str, Any],
) -> dict[str, Any]:
    agent_key = str(params.get("agent_key") or "unregistered-agent")
    raw_tools = params.get("required_tools", [])
    required_tools = tuple(str(tool) for tool in raw_tools) if isinstance(raw_tools, list) else ()
    return check_agent_availability(agent_key, required_tools=required_tools)


def _list_recent_posts(context: ToolContext, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    from app.models.foundation import Category, Tag
    from app.models.posts import Post, PostTag
    from app.modules.posts import query_service

    limit = min(max(int(params.get("limit", 10)), 1), 100)
    timeline = query_service.timeline_posts(context.session, context.user_id, limit=limit)
    ids = [uuid.UUID(item["id"]) for item in timeline["items"]]
    if not ids:
        return []
    metadata_rows = context.session.execute(
        select(Post.id, Post.published_at, Post.updated_at, Category.name)
        .outerjoin(Category, Category.id == Post.category_id)
        .where(Post.user_id == context.user_id, Post.id.in_(ids))
    ).all()
    metadata = {
        str(post_id): {
            "published_at": published_at.isoformat() if published_at else None,
            "updated_at": updated_at.isoformat(),
            "category": category,
        }
        for post_id, published_at, updated_at, category in metadata_rows
    }
    tag_rows = context.session.execute(
        select(PostTag.post_id, Tag.name)
        .join(Tag, Tag.id == PostTag.tag_id)
        .where(PostTag.user_id == context.user_id, PostTag.post_id.in_(ids))
    ).all()
    tags: dict[str, list[str]] = {}
    for post_id, tag_name in tag_rows:
        tags.setdefault(str(post_id), []).append(tag_name)
    return [
        {
            "id": item["id"],
            "title": item["title"],
            "link": f"/blog/{item['id']}/view",
            "category": metadata.get(item["id"], {}).get("category"),
            "tags": sorted(set(tags.get(item["id"], []))),
            "published_at": metadata.get(item["id"], {}).get("published_at"),
            "updated_at": metadata.get(item["id"], {}).get("updated_at"),
            "status": item["status"],
        }
        for item in timeline["items"]
    ]


def _taxonomy_statistics(context: ToolContext, params: Mapping[str, Any]) -> dict[str, Any]:
    from app.modules.posts import taxonomy_service

    kind = str(params["kind"])
    items = taxonomy_service.list_items(context.session, context.user_id, kind, enabled=True)
    key = "category" if kind == "category" else "tag"
    collection_key = "categories" if kind == "category" else "tags"
    return {
        f"{key}_count": len(items),
        collection_key: [
            {"id": item["id"], "name": item["name"], "usage_count": item["usage_count"]}
            for item in items
        ],
    }


def _read_post_bodies(context: ToolContext, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    from app.models.posts import Post

    raw_ids = params.get("post_ids", [])
    if not isinstance(raw_ids, list) or not raw_ids:
        return []
    try:
        post_ids = [uuid.UUID(str(value)) for value in raw_ids[:500]]
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "post_ids must contain UUID values",
            code="agent_tool_params_invalid",
        ) from exc
    posts = context.session.scalars(
        select(Post)
        .where(Post.user_id == context.user_id, Post.id.in_(post_ids))
        .order_by(Post.created_at, Post.id)
    ).all()
    return [{"id": str(post.id), "title": post.title, "markdown": post.markdown} for post in posts]


def _analyze_post_content(context: ToolContext, params: Mapping[str, Any]) -> dict[str, Any]:
    """Analyze one already-authorized article through the provider-neutral gateway."""
    from app.modules.agent.schemas import ContentAnalysisResult
    from app.services.llm.base import EntityRef, StructuredRequest
    from app.services.llm.gateway import get_llm_gateway

    post = params.get("post")
    if not isinstance(post, Mapping):
        raise ValidationError("post is required", code="agent_tool_params_invalid")
    post_id = str(post.get("id") or "")
    title = str(post.get("title") or "")
    markdown = str(post.get("markdown") or "")
    if not post_id or not markdown:
        raise ValidationError(
            "post id and body are required",
            code="agent_tool_params_invalid",
        )
    instruction = str(params.get("instruction") or "提取标签、关键词并生成简短摘要")
    result = get_llm_gateway().structured(
        StructuredRequest(
            scenario="agent_content_analysis",
            system=(
                "你是内容分析 Agent。只基于给定文章生成结构化结果；不得修改原文，"
                "不得声称结果已保存，不得补造文章中不存在的事实。"
            ),
            user=json.dumps(
                {
                    "post": {"id": post_id, "title": title, "markdown": markdown},
                    "instruction": instruction,
                },
                ensure_ascii=False,
            ),
            schema=ContentAnalysisResult,
            grounded_refs=[EntityRef(type="post", id=post_id)],
            temperature=0.0,
            max_tokens=1600,
            repair_attempts=1,
        )
    )
    return result.model_dump()


def _apply_post_analysis(context: ToolContext, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Apply an approved analysis preview through existing post/taxonomy services."""
    from app.models.agent import PendingWrite
    from app.modules.posts import service as post_service
    from app.modules.posts import taxonomy_service
    from app.modules.posts.schemas import PostPatch

    confirmation_id = uuid.UUID(str(params["confirmation_id"]))
    pending = context.session.get(PendingWrite, confirmation_id)
    if pending is None or pending.target_type != "post" or pending.operation_type != "update":
        raise ValidationError(
            "Confirmation is not a supported post update",
            code="agent_write_not_supported",
        )
    raw_changes = pending.preview_json.get("changes", [])
    if not isinstance(raw_changes, list):
        raise ValidationError("Invalid write preview", code="agent_write_preview_invalid")
    target_versions = {str(target["id"]): target.get("version") for target in pending.targets_json}
    results: list[dict[str, Any]] = []
    for raw_change in raw_changes:
        if not isinstance(raw_change, Mapping):
            raise ValidationError("Invalid write preview", code="agent_write_preview_invalid")
        post_id = str(raw_change.get("post_id") or "")
        target_version = target_versions.get(post_id)
        if not isinstance(target_version, int):
            raise ValidationError(
                "Write target has no optimistic version",
                code="agent_write_target_invalid",
            )

        patch_values: dict[str, Any] = {"version": target_version}
        if "summary" in raw_change:
            patch_values["summary"] = str(raw_change.get("summary") or "") or None
        for field, kind in (("tags", "tag"), ("keywords", "keyword")):
            if field not in raw_change:
                continue
            values = raw_change.get(field)
            if not isinstance(values, list):
                raise ValidationError(
                    f"{field} must be a list",
                    code="agent_write_preview_invalid",
                )
            item_ids: list[uuid.UUID] = []
            seen: set[str] = set()
            for raw_value in values:
                value = " ".join(str(raw_value or "").split())
                key = value.casefold()
                if not value or key in seen:
                    continue
                seen.add(key)
                item = taxonomy_service.resolve_name(context.session, context.user_id, kind, value)
                if item is None:
                    item = taxonomy_service.create_item(
                        context.session,
                        context.user_id,
                        kind,
                        name=value,
                    )
                item_ids.append(uuid.UUID(str(item["id"])))
            patch_values["tag_ids" if kind == "tag" else "keyword_ids"] = item_ids

        post, warnings = post_service.patch_post(
            context.session,
            context.user_id,
            uuid.UUID(post_id),
            PostPatch(**patch_values),
        )
        results.append(
            {
                "post_id": str(post.id),
                "version": post.version,
                "status": "saved",
                "warnings": warnings,
            }
        )
    return results


tool_registry.register(
    ToolDefinition(
        name="agent.capabilities",
        type="read",
        responsibility="检查 spec 006 Agent 与所需工具是否已注册并启用，不执行目标业务操作",
        required_permission=None,
        handler=_inspect_agent_capability,
    )
)
tool_registry.register(
    ToolDefinition(
        name="posts.list_recent",
        type="read",
        responsibility="按时间返回归属用户的轻量文章元数据，不读取正文",
        required_permission="posts:read",
        handler=_list_recent_posts,
    )
)
tool_registry.register(
    ToolDefinition(
        name="posts.apply_analysis",
        type="write",
        responsibility="在结构化确认后通过文章领域服务写入标签、关键词与摘要",
        required_permission="posts:write",
        handler=_apply_post_analysis,
    )
)
tool_registry.register(
    ToolDefinition(
        name="posts.read_body",
        type="read",
        responsibility="按明确的文章 ID 读取归属用户的正文，仅供内容分析任务按需使用",
        required_permission="posts:read",
        handler=_read_post_bodies,
    )
)
tool_registry.register(
    ToolDefinition(
        name="content.extract_metadata",
        type="read",
        responsibility="基于已授权的单篇文章正文生成标签、关键词与摘要提案，不写回业务数据",
        required_permission="posts:read",
        handler=_analyze_post_content,
        timeout_seconds=90.0,
        max_retries=1,
    )
)
tool_registry.register(
    ToolDefinition(
        name="taxonomy.categories",
        type="read",
        responsibility="返回文章分类及聚合使用数量",
        required_permission="posts:read",
        handler=lambda context, params: _taxonomy_statistics(
            context, {**params, "kind": "category"}
        ),
    )
)
tool_registry.register(
    ToolDefinition(
        name="taxonomy.tags",
        type="read",
        responsibility="返回文章标签及聚合使用数量",
        required_permission="posts:read",
        handler=lambda context, params: _taxonomy_statistics(context, {**params, "kind": "tag"}),
    )
)
