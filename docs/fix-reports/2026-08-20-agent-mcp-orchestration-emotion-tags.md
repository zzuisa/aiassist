# 修复复盘：Agent MCP 编排无法完成情感博客补标签（2026-08-20）

## 现象

- 用户请求“查询关于情感的博客”时，系统调用 `posts.list_recent`，返回最近文章而不是主题匹配结果。
- “8 篇”和“情感”没有稳定进入工具参数，后续步骤无法保证处理范围。
- Blog MCP 返回的是带 `structured_content` 的结构化对象，执行器只从顶层列表提取文章 ID，导致后续正文分析丢失对象范围。
- 路由阶段的远程调用与状态更新处于同一事务，首个可见进度在路由结束后才提交，前端看起来没有实时推流。
- 任务结束只返回计划步骤摘要，没有可核对的 Markdown 结果报告。

## 根因

1. 候选能力排序对 `posts.list_recent` 有硬编码加权，却没有根据输入 Schema 判断工具是否支持 `query/search`。
2. 路由完全依赖模型生成参数，没有对用户明确给出的主题与数量做确定性保留。
3. MCP 结果归一化只覆盖列表，没有递归处理 `structured_content.items`。
4. 原有 DAG 没有“筛选无标签文章”和“写后回读验证”节点，分析范围与写入后置条件都不完整。
5. MCP 连接配置为空，且进程级工具注册表错误地携带用户连接 ID，存在多用户相互覆盖风险。
6. 报告与能力目录只有规划文档，没有对应的持久化投影与前端读取链路。
7. 语义搜索兜底通过 Pydantic `model_copy(update=...)` 写入普通字符串，破坏了路由枚举类型，持久化读取 `.value` 时触发 `AttributeError`。
8. 生产安全策略仍将 DAG 最大深度限制为 4，而完整的搜索、筛选、分析、确认写入、回读验证链路深度为 5，计划校验触发 `agent_plan_too_deep`。

## 修改

- 基于工具输入 Schema 选择语义搜索能力，确定性提取 `query=情感`、`limit=8`、`cursor=0`。
- 使用固定、可恢复的 LangGraph DAG：MCP 搜索 → 检查标签 → 仅分析无标签正文 → 确认写入 → 回读验证。
- 写入预览只包含 `tags`，保留已有标签，不修改摘要和关键词；没有缺失标签时直接无写入完成。
- 递归归一化 MCP 结构化结果并生成对象范围，持久化任务能力快照和 `task-report.v1` Markdown 报告。
- 路由状态先独立提交，通过现有 SSE 推送计划与阶段；前端取消 700ms 循环轮询，展示实时计划阶段和折叠报告。
- MCP 模型可见名称统一为仅含字母、数字、下划线和连字符的稳定名称，最长 64 字符。
- MCP 授权改为按当前用户和工具键实时检查；能力快照绑定当前用户自己的连接目录版本。
- 新增第一方 Blog MCP 安全配置命令，Token 直接写入容器 secret，不输出到终端；第三方连接仍默认逐工具授权。
- 保持语义兜底路由的枚举类型，并让专用 `search_posts` 能力优先于带筛选参数的通用列表能力。
- 将仍受配置约束的 DAG 深度上限从 4 调整为 5，恰好覆盖已审核的五阶段工作流。

## 验证

- Ruff 格式化与静态检查通过。
- Mypy（排除仓库既有 `jsonschema` stubs 缺失告警）通过。
- Alembic 从空库升级到 head，并通过 `alembic check`，无模型漂移。
- 新增并通过主题/数量提取、五节点参考 DAG、仅写标签、安全名称、报告一致性、MCP 授权测试。
- 前端 TypeScript 类型检查通过；前端完整测试与生产构建在 Node 24 镜像中执行。
- 后端完整测试结果为 674 passed、1 skipped；前端完整测试结果为 179 passed，生产构建通过。
- 生产迁移版本为 `0025_complete_mcp_orchestration`，Blog MCP 状态为 healthy，当前用户可见 6 个 MCP 工具。
- 部署后提交真实用户请求，搜索参数为 `query=情感`、`limit=8`、`cursor=0`；确认预览仅包含 `tags` 字段。
- 生产报告最终统计：matched=8、processed=8、applied=8、verified=8，conflicted/failed/skipped/unprocessed 均为 0，五个计划步骤全部成功。
- 本复盘已通过 AI Assist API 归档为内部草稿文章，业务对象 ID 为 `d6b15d64-5603-4e62-bb17-9bac62c75258`，分类为“AI Assist 修复复盘”，未公开发布。

## 日志检索方式

```bash
./deploy/scripts/deploy.sh logs worker-heavy | rg 'agent_graph|plan_id|agent_plan|ERROR|exception'
./deploy/scripts/deploy.sh logs worker-fast | rg 'conversation_turn|turn_id|MCP|ERROR|exception'
./deploy/scripts/deploy.sh logs backend | rg '/api/v1/mcp/blog/mcp|agent.plan|task-report|ERROR|exception'
./deploy/scripts/deploy.sh logs nginx | rg '/api/v1/mcp/blog/mcp|/api/v1/events/jobs| 4[0-9][0-9] | 5[0-9][0-9] '
```

若消息在计划生成前失败，可使用安全业务 ID 精确检索：

```bash
./deploy/scripts/deploy.sh logs worker-heavy | rg -C 10 'conversation_turn_execution_failed|<turn_id>'
```

数据库排查只记录安全业务 ID，可按 `turn_id`、`task_id`、`plan_id` 查询
`agent_turns`、`agent_execution_plans`、`agent_plan_steps`、`agent_step_artifacts`、
`agent_task_reports`、`mcp_connections` 和 `mcp_tool_grants`。不得记录 Token、Cookie 或请求认证头。

## 遗留风险

- 标签质量仍取决于当前 LLM 配置；结构校验可保证格式，不能完全替代人工语义判断，因此写入前保留确认。
- Blog MCP Token 有有效期，过期前需要重新执行安全配置命令并重建应用容器。
- 文章在预览与确认之间被修改时会触发乐观锁冲突，报告会列入冲突项，需要重新分析。
- SSE 断线由 EventSource 自动重连；极端情况下页面会通过一次 REST 刷新补齐最终消息，不恢复高频轮询。
