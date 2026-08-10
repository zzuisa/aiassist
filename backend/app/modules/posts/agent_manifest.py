"""Code-owned system Agent manifest shared by specs 006 and 007.

The user-managed version/activation lifecycle belongs to spec 006. Until an
owner activates a user version, its data model resolves to these built-in
defaults. Runtime consumers bind the immutable ``version_ref`` and never copy
prompt/configuration content into their own tables.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from app.core.errors import NotFoundError

MANIFEST_VERSION = "blog-agents.1"


@dataclass(frozen=True, slots=True)
class RuntimeAgentBinding:
    agent_key: str
    agent_name: str
    responsibility: str
    enabled: bool
    version_ref: str


@dataclass(frozen=True, slots=True)
class _BuiltinAgent:
    agent_key: str
    agent_name: str
    responsibility: str
    enabled: bool = True


_BUILTIN_AGENTS = {
    definition.agent_key: definition
    for definition in (
        _BuiltinAgent(
            "coordinator-agent",
            "主控 Agent",
            "理解需求、选择最少能力、拆分范围并汇总独立 Agent 的真实结果",
        ),
        _BuiltinAgent(
            "article-query-agent",
            "文章查询 Agent",
            "查询、筛选和整理文章元数据，不读取文章正文",
        ),
        _BuiltinAgent(
            "editor-agent",
            "内容分析 Agent",
            "分析指定文章正文并生成结构化标签、关键词与摘要提案",
        ),
        _BuiltinAgent(
            "logic-agent",
            "逻辑分析 Agent",
            "识别文章中的结构、关系与需要质量检查的逻辑问题",
        ),
        _BuiltinAgent(
            "data-agent",
            "数据分析 Agent",
            "检查文章中的可比较数据、口径与异常项",
        ),
        _BuiltinAgent(
            "scene-image-agent",
            "场景图片 Agent",
            "在能力可用且确有理解价值时处理真实场景图片需求",
            enabled=False,
        ),
        _BuiltinAgent(
            "illustration-agent",
            "概念插画 Agent",
            "在能力可用且确有理解价值时处理概念插画需求",
            enabled=False,
        ),
    )
}


def _version_ref(definition: _BuiltinAgent) -> str:
    canonical = json.dumps(
        asdict(definition),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{MANIFEST_VERSION}:{digest}"


def resolve_builtin_agent(agent_key: str) -> RuntimeAgentBinding:
    """Resolve the effective built-in version at the spec-006 boundary."""
    definition = _BUILTIN_AGENTS.get(agent_key)
    if definition is None:
        raise NotFoundError(
            "Agent is not registered in the system manifest",
            code="blog_agent_not_registered",
        )
    return RuntimeAgentBinding(
        agent_key=definition.agent_key,
        agent_name=definition.agent_name,
        responsibility=definition.responsibility,
        enabled=definition.enabled,
        version_ref=_version_ref(definition),
    )


def registered_builtin_agents() -> tuple[RuntimeAgentBinding, ...]:
    return tuple(resolve_builtin_agent(key) for key in _BUILTIN_AGENTS)
