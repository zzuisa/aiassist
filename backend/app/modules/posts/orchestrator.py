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
3. 默认先优化文字；当文章被自动识别为“普通读者解释型文章”且流程图能降低理解成本时，自动生成一张紧凑 PNG 步骤图。不得虚构事实、数据、引用、场景或因果关系。
4. 优先局部增强，保留作者观点、语气、Markdown 结构和表达风格。
5. 相同事实只分析一次，复用共享分析；不得重复阅读全文来生成相同摘要。
6. 所有视觉内容必须通过价值门控、选项开关、能力注册、预算和数量限制；低价值时返回 skipped，不要强行生成。
7. 数字、日期、代码、命令、URL、引用和已有事实必须确定性保护；不确定内容标记 warning，不得补写。
8. 能用规则判断的事情不要额外调用 Agent；失败的非安全检查 Agent 不得使整篇文章优化失败。

诊断指标均为 0～3：information_density、logical_complexity、data_richness、scene_relevance、visual_potential、rewrite_value、evidence_quality。

门控规则：只有 logical_complexity>=2、至少 3 个有意义节点、至少 2 条正文明确关系且图示显著降低理解成本时才考虑 visualize；面向普通读者时优先生成紧凑、生活化的 visual-plan，而不是平铺的 Mermaid；只有 3～7 个节点、每个节点短标签、关系可验证时才生成。只有至少 3 个统一口径且可信的可比较数据点时才考虑 answers-charts；真实图片必须有明确地点/实物/现场语境、检索开关和来源授权；概念插画必须有明确的信息或品牌作用、生成开关，并且不能被精确图表或现有图片更好替代。任何缺少证据、只是装饰、会增加复杂度或收益低于调用成本的增强都必须 skipped。

普通读者解释型文章自动识别：标题或正文出现“是什么、为什么、如何、原理、过程、步骤、阶段、循环、从……到……、工作方式、指南、入门”等解释/过程信号，且正文至少能提取 3 个连续或相互关联的要点时，启用 reader-explainer 模式。该模式默认采用“清晰标题 + 简短导语 + 一句重点摘要 + 一张紧凑步骤 PNG + 4～6 个步骤 + 为什么重要/实际意义 + 来源”的结构；用户没有提供额外提示词也必须执行。不要输出 visual-plan 代码块给用户，系统会在候选边界将 visual-plan 渲染为真正的 PNG 并插入正文导语之后。

优先级：事实准确性 > 逻辑理解价值 > 数据表达价值 > 真实场景理解价值 > 概念插画价值 > 装饰价值。同一观点不得同时生成流程图、图表和插画。

只输出符合请求 JSON Schema 的一个 JSON 对象，不输出解释文字或 Markdown 代码围栏。最终对象必须包含 status、article_assessment、decision、optimized_article、enhancements、quality_report、usage；每个视觉增强必须包含标题/说明和 alt_text。Quality 检查只删除无依据或低价值增强，不用更多虚构内容修补。

视觉增强的 content 必须使用可执行结构：visualize 优先使用 {"visual_plan":{"visual_type":"illustrated_steps|compact_flow|concept_map|before_after|timeline","layout":"compact_horizontal|compact_vertical|timeline|radial","theme":"warm|fresh|calm|energetic|neutral","title":"...","nodes":[{"id":"step1","label":"不超过40字","detail":"不超过80字","icon":"step"}],"edges":[{"from":"step1","to":"step2","label":"不超过30字"}]}}；技术图或无法压缩时才使用 {"mermaid":"flowchart TD..."} 或 {"mermaid":"mindmap..."}。visual-plan 必须有 3～7 个节点、最多 10 条关系，节点文字短、面向普通用户、不要写代码或长段落。answers-charts 使用 {"chart_type":"bar|line|pie|scatter|table","data":[{"label":"...","value":0}],"unit":"...","source":[]}，只使用正文已有且口径一致的数据；imagegen/answers-images 使用 {"prompt":"..."} 或 {"query":"..."}。不要把 HTML、脚本、data URI 或未经验证的图片地址放入 content。

模型与工具无关：不得依赖 Claude CLI。Qwen、DeepSeek 或其他兼容 JSON Schema 的模型均按同一规则工作。"""


_CAPABILITY_DEFAULTS: tuple[dict[str, Any], ...] = (
    {
        "name": "visualize",
        "type": "skill",
        "description": "把明确的流程、层级、关系、状态变化或系统结构转成精确可读的可视化表达",
        "enabled": True,
    },
    {
        "name": "answers-charts",
        "type": "skill",
        "description": "根据文章中可靠、结构化的数值生成数据图表",
        "enabled": True,
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
    reader_explainer: bool
    reader_explainer_reason: str
    candidate_node_count: int

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


_READER_TITLE_SIGNALS = re.compile(
    r"是什么|为什么|如何|原理|过程|步骤|阶段|循环|工作方式|指南|入门|解释|从.+到|how|why|what is|process|steps?|cycle|guide",
    re.I,
)
_READER_PROCESS_SIGNALS = re.compile(
    r"首先|然后|接着|随后|最后|步骤|阶段|过程|循环|流转|演变|形成|工作原理|如何|因为|因此|所以|first|then|next|finally|step|stage|cycle|process",
    re.I,
)
_READER_RELATION_SIGNALS = re.compile(
    r"因为|因此|所以|如果|那么|导致|意味着|问题在于|无非|一方面|另一方面|此外|然而|最终|从而|叠加|依赖|无法|只有|一旦|也就是说",
    re.I,
)
_READER_DISCOURSE_PREFIX = re.compile(
    r"^(?:此外|另外|同时|然而|因此|所以|也就是说|问题在于|第一|第二|第三)[，、:：\s]+"
)


def _reader_node_candidates(content: str) -> list[str]:
    """Extract conservative, source-backed steps for the reader visual fallback."""
    candidates: list[str] = []
    for line in content.splitlines():
        value = line.strip()
        if not value or value.startswith("```") or value.startswith("!"):
            continue
        match = re.match(r"^(?:[-*]|\d+[.)、])\s+(.+)$", value)
        if match:
            candidates.append(match.group(1).strip())
    if len(candidates) >= 3:
        return candidates[:7]

    # A heading-based explainer is also common. Exclude navigation/source-only
    # headings so the generated image describes the subject, not the footer.
    for line in content.splitlines():
        match = re.match(r"^#{2,6}\s+(.+)$", line.strip())
        if match and not re.search(r"来源|参考|source|reference", match.group(1), re.I):
            candidates.append(match.group(1).strip())
    if len(candidates) >= 3:
        return candidates[:7]

    # Spoken essays and analyses often have no Markdown headings or numbered
    # list. Reuse only substantial paragraphs that explicitly express a
    # relationship, so the fallback visual remains source-backed rather than
    # inventing a summary from arbitrary prose.
    paragraphs = [
        re.sub(r"\s+", " ", part).strip()
        for part in re.split(r"\n\s*\n", content)
        if part.strip()
    ]
    paragraph_nodes = [
        paragraph
        for paragraph in paragraphs
        if len(paragraph) >= 48 and _READER_RELATION_SIGNALS.search(paragraph)
    ]
    if len(paragraph_nodes) >= 3:
        return paragraph_nodes[:5]

    return []


def detect_reader_explainer(title: str, content: str) -> tuple[bool, str, int]:
    """Identify explainers without requiring a user-authored prompt."""
    text = f"{title}\n{content}"
    nodes = _reader_node_candidates(content)
    title_signal = bool(_READER_TITLE_SIGNALS.search(title))
    process_signal_count = len(_READER_PROCESS_SIGNALS.findall(text))
    relation_count = len(_READER_RELATION_SIGNALS.findall(content))
    enough_body = len(content.strip()) >= 160
    if len(nodes) >= 3 and (title_signal or process_signal_count >= 2 or relation_count >= 2):
        reason = "标题/正文包含解释或过程信号，且已提取至少 3 个可验证要点"
        return True, reason, len(nodes)
    if enough_body and title_signal and process_signal_count >= 1 and relation_count >= 1:
        reason = "标题明确面向解释，正文包含过程关系"
        return True, reason, max(3, len(nodes))
    return False, "未达到普通读者步骤化解释的最小信息门槛", len(nodes)


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


def build_plan(
    title: str,
    content: str,
    *,
    options: dict[str, Any] | None = None,
    instruction: str | None = None,
) -> OrchestrationPlan:
    options = {
        "allow_visualize": True,
        "allow_charts": True,
        "allow_retrieved_images": False,
        "allow_generated_images": False,
        "max_agent_calls": 4,
        **(options or {}),
    }
    assessment = assess_article(title, content)
    reader_explainer, reader_reason, candidate_node_count = detect_reader_explainer(title, content)
    explicit_visual_request = bool(
        instruction
        and re.search(r"流程图|可视化|板书|脉络|因果图|决策路径|关系图", instruction)
        and not re.search(r"不要|无需|不生成|跳过", instruction)
    )
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
        (
            assessment.logical_complexity >= 2 and assessment.visual_potential >= 2
        ) or (
            explicit_visual_request
            and assessment.information_density >= 1
            and len(text_lines(content)) >= 3
        ) or (
            reader_explainer
            and candidate_node_count >= 3
            and assessment.information_density >= 1
        ),
        "逻辑节点不足，或正文信息量不足以支撑普通读者步骤图", "allow_visualize",
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
        if explicit_visual_request and "logic-agent" in selected:
            recommended.append("按用户要求将观点、因果或判断路径整理为板书式图示")

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
        reader_explainer=reader_explainer,
        reader_explainer_reason=reader_reason,
        candidate_node_count=candidate_node_count,
    )


def text_lines(content: str) -> list[str]:
    return [line.strip() for line in content.splitlines() if line.strip() and not line.lstrip().startswith("```")]


def build_default_reader_visual(
    title: str, markdown: str, plan: OrchestrationPlan
) -> dict[str, Any] | None:
    """Build a safe visual enhancement when the model omitted one.

    The fallback only reuses numbered/list or section labels already present in
    the article. It never invents a new fact, and the normal visual validator
    still gates the final PNG.
    """
    if not plan.reader_explainer or plan.candidate_node_count < 3:
        return None
    if re.search(r"!\[[^\]]*\]\([^)]*\)|```visual-plan", markdown):
        return None
    raw_nodes = _reader_node_candidates(markdown)
    if len(raw_nodes) < 3:
        return None

    nodes: list[dict[str, str]] = []
    for index, raw in enumerate(raw_nodes[:7], start=1):
        value = re.sub(r"\s+", " ", raw).strip()
        value = _READER_DISCOURSE_PREFIX.sub("", value)
        parts = re.split(r"[:：—–-]\s*", value, maxsplit=1)
        label_source = parts[0]
        if len(label_source) > 40:
            label_source = re.split(r"[，,；;。]", label_source, maxsplit=1)[0]
        label = label_source[:40].strip() or value[:40]
        detail = (parts[1] if len(parts) > 1 else value)[0:72].strip()
        nodes.append({"id": f"step{index}", "label": label, "detail": detail, "icon": "step"})
    edges = [
        {"from": nodes[index]["id"], "to": nodes[index + 1]["id"], "label": "文中关系"}
        for index in range(len(nodes) - 1)
    ]
    if re.search(r"循环|cycle", f"{title}\n{markdown}", re.I) and len(nodes) >= 3:
        edges.append({"from": nodes[-1]["id"], "to": nodes[0]["id"], "label": "再次开始"})
    return {
        "id": "auto-reader-flow",
        "agent": "logic-agent",
        "capability": "visualize",
        "status": "executed",
        "insert_after": "body",
        "reason": "系统自动识别为普通读者解释型文章，使用正文已有要点生成紧凑步骤图",
        "content": {
            "visual_plan": {
                "visual_type": "compact_flow",
                "layout": "compact_horizontal" if len(nodes) <= 5 else "compact_vertical",
                "theme": "fresh",
                "title": (title or "文章关键脉络")[:80],
                "nodes": nodes,
                "edges": edges,
            }
        },
        "caption": "文章关键脉络（基于作者观点）",
        "alt_text": f"{title}的关键脉络示意图"[:500],
    }


def has_embedded_visual(markdown: str) -> bool:
    """Return whether the article already contains an AI Assist visual asset."""
    return bool(
        re.search(r"/api/v1/posts/[^)]+/visual-assets/[^)]+\.png", markdown)
        or "```visual-plan" in markdown
    )


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
            "reader_mode": "reader_explainer" if plan.reader_explainer else "standard",
            "reader_mode_reason": plan.reader_explainer_reason,
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
    if plan.reader_explainer:
        parts.append(
            "本次已自动启用 reader-explainer 模式：请把正文整理成普通读者能快速理解的短段落、步骤和实际意义；"
            "优先返回一张 3～7 节点的紧凑 visual_plan。节点只能来自原文已表达的事实，标签简短，"
            "不要返回 Mermaid、代码围栏或下载按钮。"
        )
    if "logic-agent" in plan.selected_agents:
        parts.append(
            "本次优化已将读者示意图列为固定增强步骤。请在 enhancements 中返回一项 status=executed、"
            "capability=visualize 的紧凑 visual_plan；仅使用原文事实，控制在 3～5 个节点，"
            "每个节点只保留短标题和一句细节，避免大段文字。系统会将其渲染为 PNG 并插入候选正文，"
            "不要返回图片 URL、base64 或下载按钮。"
        )
    if instruction:
        parts.append(f"用户本次附加要求（仅在不改变事实和作者意图时执行）：{instruction}")
    return "\n\n".join(parts)
