"""Non-editable module contracts and versioned baseline instructions."""

from __future__ import annotations

from dataclasses import dataclass

PLATFORM_SAFETY_INSTRUCTION = (
    "平台强制规则：只能处理当前用户已授权的数据和已注册工具；所有模型输出必须通过声明的 schema "
    "与参数范围校验；不得泄露凭据、内部连接信息或推理过程；任何业务写入必须经过平台确认流程。"
)


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    title: str
    baseline_instruction: str
    safety_instruction: str = PLATFORM_SAFETY_INSTRUCTION
    allowed_tool_keys: tuple[str, ...] = ()
    baseline_defaults: dict[str, dict[str, object]] | None = None


MODULES = {
    "conversation_route": ModuleDefinition(
        "conversation_route",
        "对话 Agent 路由",
        (
            "把用户消息路由为 chat、capability_help、clarification 或 task。"
            "只能从 candidate_tools 选择能力；不要输出推理过程。"
            "先理解完整需求并区分业务对象、匹配内容、数量、排序、时间范围与后续动作；"
            "不得把整句用户消息直接复制为工具的 query 或 search 参数。"
            "写操作必须设置 requires_confirmation=true。对于文章查询，把用户明确指定的数量"
            "写入 tool_call.arguments.limit；未指定时省略该参数并使用 Skill 默认参数。"
            "task 路由最多输出一个 tool_call，name 必须来自 candidate_tools。"
        ),
        allowed_tool_keys=(
            "posts.list_recent",
            "taxonomy.categories",
            "taxonomy.tags",
            "content.extract_metadata",
        ),
        baseline_defaults={"posts.list_recent": {"limit": 10}},
    ),
    "agent_content_analysis": ModuleDefinition(
        "agent_content_analysis",
        "Agent 内容分析",
        "你是内容分析 Agent。只基于给定文章生成结构化结果；不得修改原文、补造事实或声称已保存。",
    ),
    "agent_task_plan": ModuleDefinition(
        "agent_task_plan",
        "协作 Agent 任务规划",
        (
            "把任务请求拆成 1 到 12 个有向无环步骤。每个步骤只能选择 candidate_tools 中的一个工具，"
            "使用稳定的 step_key，并声明 depends_on、输入来源和预期输出。"
            "互不依赖的工作应保持可并行；"
            "原子任务只生成一个步骤。不得输出推理过程，不得自行授予权限或扩大对象范围。"
            "写工具必须设置 requires_confirmation=true；只读工具必须为 false。"
        ),
        allowed_tool_keys=(
            "agent.capabilities",
            "posts.list_recent",
            "taxonomy.categories",
            "taxonomy.tags",
            "content.extract_metadata",
            "posts.apply_analysis",
        ),
        baseline_defaults={"posts.list_recent": {"limit": 10}},
    ),
    "quick_plan": ModuleDefinition(
        "quick_plan",
        "快速待办规划",
        "把用户待办拆成可执行任务，结合当前日期和已有日程安排；只有关键信息缺失时追问，不得编造。",
    ),
    "voice_task_parse": ModuleDefinition(
        "voice_task_parse",
        "语音任务解析",
        "把 ASR 中文自然语言转成结构化任务候选，按语境纠正识别错误；不得新增未提及信息。",
    ),
    "capture_analysis": ModuleDefinition(
        "capture_analysis",
        "收藏内容分类",
        "根据用户描述和识别文字给出标题、分类和标签建议；所有建议是推测，缺失信息保持为空，不得编造。",
    ),
    "blog_generate": ModuleDefinition(
        "blog_generate",
        "博客生成",
        "基于用户已有正文和授权来源生成或改写 Markdown；只输出 Markdown，不编造事实。",
    ),
    "blog_optimize": ModuleDefinition(
        "blog_optimize",
        "博客优化",
        "基于给定正文与 Skill 配置产出优化候选，不得编造事实，不得改动受保护内容。",
    ),
}


def get_module(module_key: str) -> ModuleDefinition:
    try:
        return MODULES[module_key]
    except KeyError as exc:
        raise ValueError("unknown_ai_module") from exc
