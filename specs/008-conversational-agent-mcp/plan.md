# Implementation Plan: 对话式 Agent 与 MCP 任务路由

**Branch**: `007-conversational-agent-mcp` | **Date**: 2026-08-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-conversational-agent-mcp/spec.md`

## Summary

在现有自助 Agent 的任务、状态、审计和结构化确认能力之上增加持久化会话层。每条消息先可靠保存，再由对话路由器把它判定为普通对话、能力说明、必要澄清或业务任务。业务任务使用安全能力清单选择内置工具或已配置、已授权的 MCP 工具；确定性策略在执行前再次检查可用性、权限、读写性质、范围和参数结构。所有写操作继续复用 `PendingWrite` 确认边界。

MCP 只在后端通过官方客户端访问预配置的 Streamable HTTP 服务。首版不接受用户输入任意服务器 URL、不启动 stdio 子进程、不在浏览器保存凭据。MCP 返回值按不可信外部数据处理，不得自行触发第二次工具调用。对话与任务状态继续复用现有 SSE 和 Job 事实源，并补齐顶层异常终态与停滞 watchdog。

**Implementation baseline dependency**: 本分支从 `master` 创建，尚未包含已在 `006-agent-content-management` 分支完成的自助 Agent 基线。实施前必须集成该分支截至 `d70e39c` 的 Agent 运行时、前端入口和迁移 `0019_agent_runtime`；本计划是对该基线的增量，不重写它。

## Technical Context

**Language/Version**: Python 3.12.x；TypeScript 5.7.x；Node.js 24 LTS

**Primary Dependencies**: FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、Celery、HTTPX、官方 MCP Python SDK 2.x；Vue 3、Pinia、Vue Router、Naive UI

**Storage**: PostgreSQL 保存会话、消息、路由决定、任务关联、MCP 非敏感元数据、授权与最终状态；RabbitMQ/Celery 执行异步路由和工具调用；Redis 仅作 SSE 唤醒、短期锁与清单缓存。MCP 端点和凭据通过只读 secrets 配置文件注入，不进入业务表。

**Testing**: pytest unit/contract/integration/security/reliability/performance；Vitest 组件测试；Playwright 对话 E2E；MCP 官方测试 server 或协议 stub 进行契约与故障注入

**Target Platform**: Linux 个人服务器，Docker Compose 单机自托管；现代移动端和桌面浏览器

**Project Type**: 前后端分离 Web/PWA + 模块化单体 API + 既有异步 Worker

**Performance Goals**: 普通问候 p95 3 秒内完成；消息接受 p95 1 秒；任务型消息 2 秒内出现首个阶段状态；能力清单最多 100 个工具时路由 p95 3 秒；停滞任务在配置阈值后 60 秒内转为可操作状态

**Constraints**: 不新增服务进程或队列类型；不新增 WebSocket；不开放任意 MCP URL 或 stdio；所有模型输出和 MCP 参数均结构化校验；工具输出上限默认 256 KiB；写入必须结构化确认；提示词、状态、记录和日志不得出现端点或凭据

**Scale/Scope**: 最多 5 个账户、每用户 1,000 个会话、每会话 1,000 条消息、最多 20 个 MCP 连接/用户、100 个可见工具；首版只支持服务端 Streamable HTTP MCP 工具调用，不实现 MCP Apps、prompts、resources、sampling、roots 或协议 Tasks 扩展

## Constitution Check

*GATE: Passed before Phase 0 and re-checked after Phase 1 design.*

**Constitution version**: 1.1.0。此次修订从延期列表移除 MCP，同时增加工具安全清单、类型校验、最小权限、脱敏审计和禁止伪造的强制规则。

- [x] 用户消息在路由模型或后台任务前落库；任务创建与触发事件同事务。
- [x] 所有内部或 MCP 写操作生成 `PendingWrite`，批准后重新校验所有权、版本、权限和工具可用性。
- [x] 仍为模块化单体和既有 Compose 进程；MCP 是 provider-neutral gateway，不增加业务服务。
- [x] LLM 与 MCP 均经过类型化 gateway、超时、有界重试、稳定错误和版本化 schema。
- [x] PostgreSQL 是消息、Turn、Task 与 Job 状态事实源；含幂等键、outbox、DLQ、锁、顶层异常终态和 watchdog。
- [x] 每次查询和调用重新检查用户归属及 tool grant；凭据只从 secrets provider 解析。
- [x] REST、SSE、路由模型输出和安全工具清单均有版本化契约。
- [x] 每个用户故事先安排测试，并覆盖 MCP 离线、恶意输出、重启、未确认零写入和数据存活。
- [x] 用户看到对话、阶段、能力名称和可行动错误，不暴露队列、协议会话、隐藏推理或凭据。

**Post-design result**: PASS。设计未采用任意 URL、浏览器直连、stdio 或自动权限提升；无 Constitution 例外。

## Phase 0 Research Decisions

完整记录见 [research.md](./research.md)。关键决定：

1. 使用“两段式路由”：纯问候和能力说明走确定性快路径；其他消息生成 `conversation-route.v1` 结构化决定，再由策略层校验，避免继续扩展关键词分类器。
2. 工具选择只基于安全清单。先用名称/职责/权限做确定性候选缩减，再让模型在候选中选择；选定后才提供其验证过的参数 schema。
3. MCP 采用官方 Python SDK 2.x 的服务端 Streamable HTTP client；依赖 SDK 的旧协议兼容，不自行实现 JSON-RPC。
4. MCP 输出一律视为不可信数据，做大小、媒体类型与结果 schema 检查；工具结果不能自动改变计划或触发写入。
5. 每条消息对应一个持久化 Turn。后台顶层异常必须写终态；周期 watchdog 将无心跳的 Turn/Task 标记为 stalled 并提供幂等重试。

## Project Structure

### Documentation (this feature)

```text
specs/008-conversational-agent-mcp/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── openapi.yaml
│   └── schemas/
│       ├── conversation-route.v1.json
│       ├── conversation-event.v1.json
│       └── safe-tool-manifest.v2.json
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/0020_conversational_agent.py
├── app/
│   ├── models/agent_conversation.py
│   ├── modules/agent/
│   │   ├── conversation_router.py
│   │   ├── conversation_service.py
│   │   ├── conversation_schemas.py
│   │   ├── capability_selector.py
│   │   ├── watchdog.py
│   │   ├── router.py                    # extend existing REST boundary
│   │   ├── registry.py                  # extend safe manifest/policy checks
│   │   └── service.py                   # reuse AgentTask/PendingWrite lifecycle
│   ├── services/mcp/
│   │   ├── base.py
│   │   ├── config.py
│   │   ├── gateway.py
│   │   └── provider.py
│   └── workers/tasks/agent.py            # add Turn execution/finalizer
└── tests/{unit,contract,integration,security,reliability,performance}/

frontend/
├── src/
│   ├── api/agentConversations.ts
│   ├── components/agent/
│   │   ├── ConversationMessage.vue
│   │   ├── ConversationTimeline.vue
│   │   ├── ClarificationCard.vue
│   │   └── ToolActivityCard.vue
│   ├── modules/agent/AgentPage.vue       # replace single-task form with conversation UI
│   └── stores/agentConversations.ts
└── tests/{component,e2e}/

deploy/
└── secrets/mcp-connections.example.json
```

**Structure Decision**: 对话编排继续位于既有 `agent` 业务模块；MCP 连接协议放入 provider-neutral service gateway。浏览器只与本应用 REST/SSE 通信。现有 `/agent/tasks` 和确认端点保留兼容，新会话端点通过同一任务与写入服务复用安全边界。

## Transaction and Execution Boundaries

1. 接收消息事务写入 Conversation、用户 Message、Turn、Job 与 outbox；返回稳定 ID。
2. Worker 读取持久化消息和最小会话上下文，生成并校验路由决定。
3. 普通对话写入 assistant Message 并结束 Turn；澄清写入 question Message 并等待下一条用户消息。
4. 任务路由绑定现有 AgentTask；能力选择器校验安全清单、grant、读写类型和参数。
5. 只读工具执行后写 ExecutionRecord 与 assistant Message。写工具只能生成 PendingWrite；批准后由既有确认端点恢复执行。
6. 任一异常由 worker finalizer 在独立事务中将 Turn、Task 和 Job 转为明确终态。watchdog 处理进程在终态提交前退出的情况。

## MCP Security Boundary

- 连接由 operator secrets 文件预配置；数据库只存 `config_key`、显示名、状态和工具快照。
- 首版仅允许 Streamable HTTP；配置加载时验证协议、主机 allowlist 和重定向目标，用户消息不能改变端点。
- 每个工具以 `mcp.<connection_key>.<tool_name>` 注册，输入 schema 规范化为 JSON Schema 2020-12；不支持的 schema 标记 unavailable。
- 发送给模型的内容不含 endpoint、auth header、server instructions 或 connection string。
- OAuth/token 由 provider 从 secret reference 获取；禁止 token passthrough，令牌必须绑定目标资源。
- MCP 内容最大 256 KiB，超限截断为安全摘要并记录；未知媒体和二进制不进入模型。
- 写工具在调用前生成本地预览。无法提前确定影响范围的 MCP 写工具首版标记 unavailable。

## Complexity Tracking

无 Constitution 例外。MCP 增加了外部边界，但它直接满足用户要求，并复用单一 typed gateway、现有 worker、Job、SSE 和确认机制；未增加微服务、浏览器协议客户端、通用插件安装器或第二套任务系统。
