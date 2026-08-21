# 修复复盘：Agent LLM 路由被关键词规则覆盖（2026-08-21）

## 现象

用户输入“查询最近3篇内容含有女人的文章”后，Agent 任务在技术状态上显示执行成功，但博客搜索返回 0 条结果。数据库检查确认存在多篇正文包含“女人”的文章，因此结果与用户预期不符。

## 根因

对话路由阶段实际已经调用 LLM，并获得结构化路由结果；但随后又执行了一套本地关键词和正则推断逻辑。该逻辑把完整自然语言片段“最近3篇内容含有女人”覆盖到博客 MCP 的 `query` 参数中，而不是保留语义条件 `query=女人`、`limit=3`。

此外，候选工具在调用 LLM 前还会被关键词打分裁剪，使 LLM 不能基于当前完整、已授权的 MCP 能力清单自主编排。SiliconFlow OpenAI 兼容适配器也未显式开启当前模型已经支持的 thinking 能力。

## 修改

1. 删除业务请求的关键词意图识别、候选工具关键词评分和 LLM 结果二次覆盖逻辑。
2. 将当前全部可用且已授权的安全工具清单交给 LLM，由 LLM 输出结构化的工具、目标和参数决策。
3. 删除计划生成阶段基于“然后、标签、没有则”等词语的复杂度判断和固定工作流；所有业务任务均由 LLM 决定生成单步计划或 DAG。
4. 旧 `/agent/tasks` 兼容入口的新任务统一标记为 `llm.route`，在异步 Worker 内同样执行 LLM 路由和计划；旧 intent 注册仅用于读取和执行历史任务。
5. 强化路由提示契约，要求分别识别业务对象、检索条件、数量、排序、时间范围和后续动作，禁止把整句需求直接复制到单个搜索参数。
6. 在 SiliconFlow 的 `DeepSeek-V3.2` 路由和计划请求上启用 thinking，并设置有限的 reasoning budget；其他模型供应商保持兼容。
7. 保留工具存在性、JSON Schema、权限、DAG 和确认策略等确定性后置校验。这些校验只负责安全与契约，不再推断用户意图。
8. 不保存、不向前端输出模型原始 `reasoning_content`；前端与审计链路继续使用可验证的结构化决策、计划节点、工具参数和执行结果。

## 验证

- 路由、计划、网关与模型适配器定向测试：14 项全部通过。
- 移除旧入口关键词分类后，Agent 单元、集成与契约回归测试：82 项全部通过。
- 后端相关完整测试：672 项通过；3 项性能专项测试按既有参数排除，1 项消息代理测试因本地测试环境未连接 RabbitMQ 而跳过。
- 修改文件 Ruff 检查与格式检查通过，`git diff --check` 通过。
- 使用生产配置的真实 `DeepSeek-V3.2` 和同步后的 MCP 清单验证，模型输出：

  ```json
  {
    "selected_tool": "roguelife-blog-blog_search_posts",
    "objective": "搜索内容含有‘女人’的最近3篇文章",
    "arguments": {
      "query": "女人",
      "limit": 3
    },
    "route_kind": "task"
  }
  ```

- 数据核验确认当前博客库中存在 10 篇 Markdown 内容匹配“女人”的文章。

## 日志检索方式

部署环境可使用以下命令查看 Agent 编排、LLM 请求和异常：

```bash
./deploy/scripts/deploy.sh logs worker-heavy | rg 'execute_conversation_turn|coordinate_plan|HTTP Request|conversation_turn_execution_failed|ERROR|exception'
```

需要核对结构化决策时，按安全业务对象 ID 查询 `agent_routing_decisions`、`agent_plan_steps` 和 `agent_step_artifacts`；不要在日志或复盘中复制认证信息。

## 内部文章归档

- 分类：AI Assist 修复复盘
- 文章 ID：`49adb055-16e7-4d31-83cd-4aea73c3f00e`
- 可见性：AI Assist 内部，未公开发布

## 遗留风险

1. Thinking 会增加少量路由延迟和模型用量，当前使用受限预算控制。
2. LLM 的决策质量依赖 MCP 工具名称、说明和参数 Schema 的准确性；新增 MCP 时仍需完善契约与回归用例。
3. MCP 连接必须先同步成功，否则模型只能看到内部工具。
4. 模型输出不满足结构化契约时，系统会进入修复或澄清路径，而不会由关键词规则兜底猜测。
5. “最近”的最终排序仍取决于博客 MCP 的排序语义；后续可将发布时间与更新时间定义得更明确。
