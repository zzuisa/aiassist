# ruff: noqa: E501

"""Value-gated orchestration for the Blog Enhancement flow.

The orchestrator is deliberately provider-neutral.  It owns the shared
diagnosis, budget and capability gates; the LLM gateway remains responsible for
calling the configured model and validating its structured response.  Skills
are described by a small environment-injected registry so adding an HTTP/MCP
adapter does not require changing the article worker.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from app.core.config import get_settings

BLOG_ENHANCEMENT_SYSTEM_PROMPT = r"""你是「AI Assist 博客增强编排器（Blog Enhancement Orchestrator）」。

你的任务不是把文章改得更长，也不是为了展示能力而调用工具，而是在控制成本、尊重作者原意和保证事实可靠的前提下，判断文章是否值得优化，并调用已经注册且允许使用的专业 Agent 与 Skill 丰富正文。

必须遵守：
1. 先诊断价值，再决定是否执行；skipped 是正常结果。
2. Agent 负责分析和决策，Skill/MCP 负责执行具体能力；不得假设模型原生拥有 Skill。
3. 默认只优化文字，不生成图片；不得虚构事实、数据、引用、场景或因果关系。
4. 优先局部增强，保留作者观点、语气、Markdown 结构和表达风格。
5. 相同事实只分析一次，复用共享分析；不得重复阅读全文来生成相同摘要。
6. 所有视觉内容必须通过价值门控、选项开关、能力注册、预算和数量限制；低价值时返回 skipped，不要强行生成。
7. 数字、日期、代码、命令、URL、引用和已有事实必须确定性保护；不确定内容标记 warning，不得补写。
8. 能用规则判断的事情不要额外调用 Agent；失败的非安全检查 Agent 不得使整篇文章优化失败。

诊断指标均为 0～3：information_density、logical_complexity、data_richness、scene_relevance、visual_potential、rewrite_value、evidence_quality。

门控规则：只有 logical_complexity>=2、至少 3 个有意义节点、至少 2 条正文明确关系且图示显著降低理解成本时才考虑 visualize；只有至少 3 个统一口径且可信的可比较数据点时才考虑 answers-charts；真实图片必须有明确地点/实物/现场语境、检索开关和来源授权；概念插画必须有明确的信息或品牌作用、生成开关，并且不能被精确图表或现有图片更好替代。任何缺少证据、只是装饰、会增加复杂度或收益低于调用成本的增强都必须 skipped。

优先级：事实准确性 > 逻辑理解价值 > 数据表达价值 > 真实场景理解价值 > 概念插画价值 > 装饰价值。同一观点不得同时生成流程图、图表和插画。

只输出符合请求 JSON Schema 的一个 JSON 对象，不输出解释文字或 Markdown 代码围栏。最终对象必须包含 status、article_assessment、decision、optimized_article、enhancements、quality_report、usage；每个视觉增强必须包含标题/说明和 alt_text。Quality 检查只删除无依据或低价值增强，不用更多虚构内容修补。

模型与工具无关：不得依赖 Claude CLI。Qwen、DeepSeek 或其他兼容 JSON Schema 的模型均按同一规则工作。"""


_CAPABILITY_DEFAULTS: tuple[dict[str, Any], ...] = (
    {
        "name": "visualize",
        "type": "skill",
        "description": "把明确的流程、层级、关系、状态变化或系统结构转成精确可读的可视化表达",
    },
    {
        "name": "answers-charts",
        "type": "skill",
        "description": "根据文章中可靠、结构化的数值生成数据图表",
    },
    {
        "name": "answers-images",
        "type": "skill",
        "description": "检索帮助理解真实地点、实物、人物或现场环境的图片",
    },
    {
        "name": "imagegen",
        "type": "skill",
        "description": "生成概念插画、封面或无法通过精确图表表达的视觉内容",
    },
)


@dataclass(frozen=True)
class Assessment:
    information_density: int
    logical_complexity: int
    data_richness: int
    scene_relevance: int
    visual_potential: int
    rewrite_value: int
    evidence_quality: int


@dataclass(frozen=True)
class OrchestrationPlan:
    assessment: Assessment
    article_summary: str
    key_points: list[str]
    logical_relations: list[str]
    verified_data_points: list[str]
    weak_sections: list[str]
    unsupported_claims: list[str]
    recommended_actions: list[str]
    selected_agents: list[str]
    skipped_agents: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["article_assessment"] = asdict(self.assessment)
        del data["assessment"]
        return data


def registered_capabilities() -> list[dict[str, Any]]:
    """Return the safe public capability manifest.

    ``BLOG_CAPABILITIES_JSON`` can contain a list of capability objects.  Only
    manifest fields are passed to the model; endpoints and credentials are
    intentionally never included in prompts or logs.
    """

    raw = get_settings().blog_capabilities_json.strip()
    configured: Any = None
    if raw:
        try:
            configured = json.loads(raw)
        except json.JSONDecodeError:
            configured = None
    by_name = {item["name"]: dict(item) for item in _CAPABILITY_DEFAULTS}
    if isinstance(configured, list):
        for item in configured:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            name = item["name"]
            if name not in by_name:
                by_name[name] = {"name": name, "type": "skill", "description": "已注册能力"}
            by_name[name].update(
                {
                    key: item[key]
                    for key in ("type", "description", "enabled")
                    if key in item
                }
            )
    return [
        {**item, "enabled": bool(item.get("enabled", False))}
        for item in by_name.values()
    ]


def _score(value: int) -> int:
    return max(0, min(3, value))


def assess_article(title: str, content: str) -> Assessment:
    """Perform cheap deterministic diagnosis before spending a model call."""

    text = content.strip()
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    headings = re.findall(r"^#{1,6}\s+.+$", text, flags=re.MULTILINE)
    sentences = re.findall(r"[^。！？.!?\n]+[。！？.!?]", text)
    numbers = re.findall(r"(?<![A-Za-z])\d+(?:[.,]\d+)?%?", text)
    relations = re.findall(
        r"因为|因此|所以|导致|如果|然后|首先|其次|最后|相比|从而|依赖|->|=>",
        text,
    )
    scene_words = re.findall(
        r"北京|上海|深圳|广州|杭州|地点|现场|建筑|街道|房间|设备|产品|实物|照片|旅行|博物馆|餐厅",
        f"{title}\n{text}",
    )
    information_density = _score(
        (2 if len(text) >= 240 else 1 if len(text) >= 80 else 0)
        + (1 if len(paragraphs) >= 3 else 0)
    )
    logical_complexity = _score(
        (1 if len(headings) >= 2 else 0)
        + (1 if len(relations) >= 2 else 0)
        + (1 if len(paragraphs) >= 4 else 0)
    )
    data_richness = _score((1 if len(numbers) >= 3 else 0) + (1 if len(numbers) >= 6 else 0))
    scene_relevance = _score((2 if len(scene_words) >= 2 else 1 if scene_words else 0) + (1 if "http" not in text else 0))
    visual_potential = _score(
        (2 if logical_complexity >= 2 else 0)
        + (1 if data_richness >= 2 else 0)
    )
    rewrite_value = _score(
        (1 if len(text) >= 120 else 0)
        + (1 if any(len(part) > 420 for part in paragraphs) else 0)
        + (1 if len(sentences) >= 8 and len(headings) == 0 else 0)
    )
    evidence_quality = _score(
        (1 if len(text) >= 120 else 0)
        + (1 if numbers or "http" in text else 0)
        + (1 if len(paragraphs) >= 3 else 0)
    )
    return Assessment(
        information_density=information_density,
        logical_complexity=logical_complexity,
        data_richness=data_richness,
        scene_relevance=scene_relevance,
        visual_potential=visual_potential,
        rewrite_value=rewrite_value,
        evidence_quality=evidence_quality,
    )


def build_plan(title: str, content: str, *, options: dict[str, Any] | None = None) -> OrchestrationPlan:
    options = {
        "allow_visualize": True,
        "allow_charts": True,
        "allow_retrieved_images": False,
        "allow_generated_images": False,
        "max_agent_calls": 4,
        **(options or {}),
    }
    assessment = assess_article(title, content)
    capabilities = {item["name"]: item for item in registered_capabilities()}
    max_calls = max(1, min(8, int(options.get("max_agent_calls", 4))))
    selected: list[str] = []
    skipped: list[dict[str, str]] = []

    if assessment.rewrite_value >= 1:
        selected.append("editor-agent")
    else:
        skipped.append({"agent": "editor-agent", "reason_code": "LOW_REWRITE_VALUE", "reason": "原文已经足够短或清晰"})

    def consider_visual(agent: str, capability: str, condition: bool, reason: str, option: str) -> None:
        if not condition:
            skipped.append({"agent": agent, "reason_code": "INSUFFICIENT_VALUE", "reason": reason})
            return
        if not bool(options.get(option, False)):
            skipped.append({"agent": agent, "reason_code": "DISABLED_BY_OPTION", "reason": f"{option}=false"})
            return
        if not capabilities.get(capability, {}).get("enabled", False):
            skipped.append({"agent": agent, "reason_code": "CAPABILITY_UNAVAILABLE", "reason": f"{capability} 未注册或未启用"})
            return
        if len(selected) >= max_calls:
            skipped.append({"agent": agent, "reason_code": "AGENT_BUDGET_EXCEEDED", "reason": "超过 max_agent_calls"})
            return
        selected.append(agent)

    consider_visual(
        "logic-agent", "visualize",
        assessment.logical_complexity >= 2 and assessment.visual_potential >= 2,
        "逻辑节点或关系不足以降低理解成本", "allow_visualize",
    )
    consider_visual(
        "data-agent", "answers-charts",
        assessment.data_richness >= 2 and assessment.evidence_quality >= 2,
        "没有足够的统一口径可靠数据", "allow_charts",
    )
    consider_visual(
        "scene-image-agent", "answers-images",
        assessment.scene_relevance >= 2,
        "没有明确且有真实图片价值的场景", "allow_retrieved_images",
    )
    consider_visual(
        "illustration-agent", "imagegen",
        assessment.visual_potential >= 2,
        "概念插画不能提供高于文字或精确图示的理解价值", "allow_generated_images",
    )

    if not selected and assessment.rewrite_value == 0:
        recommended = ["保持原文，不进行低价值扩写"]
    else:
        recommended = ["仅应用通过质量检查的局部文字优化"]
        if any(item in selected for item in ("logic-agent", "data-agent")):
            recommended.append("视觉内容必须附标题、说明和 alt text")

    key_points = [line.strip(" -*") for line in text_lines(content)[:8]]
    summary = (content.strip().replace("\n", " ")[:240] or title.strip())
    return OrchestrationPlan(
        assessment=assessment,
        article_summary=summary,
        key_points=key_points,
        logical_relations=["正文包含明确关系" for _ in range(min(3, len(re.findall(r"因为|因此|所以|如果|然后|首先|其次|最后|相比|从而", content))))],
        verified_data_points=re.findall(r"(?<![A-Za-z])\d+(?:[.,]\d+)?%?", content)[:12],
        weak_sections=[],
        unsupported_claims=[],
        recommended_actions=recommended,
        selected_agents=selected[:max_calls],
        skipped_agents=skipped,
    )


def text_lines(content: str) -> list[str]:
    return [line.strip() for line in content.splitlines() if line.strip() and not line.lstrip().startswith("```")]


def build_user_payload(
    *, title: str, content: str, language: str, category: str | None,
    target_audience: str | None, author_intent: str | None,
    options: dict[str, Any], skill_config: dict[str, Any], plan: OrchestrationPlan,
) -> str:
    payload = {
        "article": {
            "title": title,
            "content": content,
            "language": language,
            "category": category or "",
            "target_audience": target_audience or "",
            "author_intent": author_intent or "",
        },
        "options": {
            "mode": "balanced",
            "preserve_author_style": True,
            "allow_rewrite": True,
            "allow_web_search": False,
            "allow_visualize": True,
            "allow_charts": True,
            "allow_retrieved_images": False,
            "allow_generated_images": False,
            "max_visual_items": 2,
            "max_agent_calls": 4,
            "cost_priority": "high",
            **options,
        },
        "available_capabilities": registered_capabilities(),
        "skill_config": skill_config,
        "shared_analysis": plan.as_dict(),
    }
    return json.dumps(payload, ensure_ascii=False)


def build_system_prompt(config: dict[str, Any], plan: OrchestrationPlan, instruction: str | None) -> str:
    rules: list[str] = []
    for key in ("content_rules", "title_rules", "summary_rules", "body_structure", "prohibitions"):
        rules.extend(str(item) for item in config.get(key, []) or [])
    parts = [BLOG_ENHANCEMENT_SYSTEM_PROMPT]
    if rules:
        parts.append("当前 Skill 的附加规则（不得违反总控安全规则）：\n" + "\n".join(f"- {rule}" for rule in rules))
    parts.append("本次共享诊断已由总控生成，请直接复用，不要再次摘要：\n" + json.dumps(plan.as_dict(), ensure_ascii=False))
    if instruction:
        parts.append(f"用户本次附加要求（仅在不改变事实和作者意图时执行）：{instruction}")
    return "\n\n".join(parts)
