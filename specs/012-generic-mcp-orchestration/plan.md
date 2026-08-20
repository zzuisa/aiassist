# Implementation Plan: 通用 MCP 任务编排与报告

**Branch**: `012-generic-mcp-orchestration` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/012-generic-mcp-orchestration/spec.md`

## Summary

在 011 已交付的 Agent 任务、MCP 网关、写入确认和 SSE 计划视图之上，引入 LangGraph 作为唯一编排运行时，替换现有自研 scheduler 的依赖计算、步骤推进、重试和恢复逻辑。LangGraph 使用 PostgreSQL Checkpointer 持久化 Graph State；现有 Agent Plan 表仅作为面向用户和审计的投影，不再与 LangGraph 竞争运行时状态真相。首个端到端场景通过已授权的博客查询与分类能力搜索情感文章、筛选未分类对象、从现有分类中生成建议，经批量确认后按对象版本安全写入，再回读对账并返回报告。

继续使用现有 modular monolith、Celery、事务 Outbox、REST 与 SSE；Celery/Outbox 只负责可靠启动或恢复一次 Graph Run，不再实现第二套 DAG 调度器。OpenUI 仅保留为未来读取安全报告数据的可选展示实验，不参与执行、确认或真实状态控制。

## Technical Context

**Language/Version**: Python 3.12；TypeScript 5.7；Node 24

**Primary Dependencies**: FastAPI、SQLAlchemy 2、Alembic、Pydantic 2、LangGraph、LangGraph PostgreSQL Checkpointer、Celery 5.6、PostgreSQL、Redis、RabbitMQ、官方 MCP Python SDK 2、jsonschema、Vue 3、Pinia、现有 Markdown 安全渲染与 SSE Job 流

**Storage**: PostgreSQL 保存 LangGraph Checkpoint、能力快照、计划投影、步骤投影、批次/逐项执行结果、产物、尝试、写入预览、验证结果和报告；Redis 仅用于短期锁/缓存；RabbitMQ 传递由事务 Outbox 发布的 Graph start/resume 命令

**Testing**: pytest 单元、契约、集成、可靠性、安全与性能测试；Vitest 组件测试；Playwright Agent 端到端测试；Alembic 升降级与漂移检查

**Target Platform**: 现有 Docker Compose 单机部署，继续使用 backend、frontend、worker-fast、worker-heavy 与 beat

**Project Type**: 前后端 Web 应用、异步工作进程与内部 MCP 服务

**Performance Goals**: 95% 正常任务 2 秒内显示计划或能力缺口；95% 状态变化 2 秒内可见；最多 1,000 篇文章分页/分批无遗漏去重；终态后 5 秒内产生确定性报告；独立步骤并发上限默认 4

**Constraints**: 每计划最多 12 个可见步骤、深度 4；每批最多 100 项、总范围默认最多 1,000 项；MCP 单次结果默认最多 256 KiB；Graph Node 最多 2 次执行尝试；写入必须冻结预览并单独确认；外部写入结果不等同验证成功；不把 Prompt、推理、正文、凭据、端点或原始 MCP 响应写入事件和报告

**Scale/Scope**: 单用户个人服务器；每用户最多 20 个 MCP 连接、规划最多看到 100 个安全能力；首期覆盖通用 select/map/filter/aggregate/analyze/mutate/verify/report 责任和博客分类完整场景，不支持递归 Agent、动态代码表达式、自动新建分类或破坏性冲突回退

## Constitution Check

*GATE: Passed before Phase 0 research. Re-checked after Phase 1 design.*

- [x] User content is durably persisted before AI or other long-running work starts.
- [x] AI mutations are previewed/confirmed, reversible, and never move fixed events.
- [x] Design remains a modular monolith deployable through Docker Compose.
- [x] AI, speech, mail, and storage integrations use provider-neutral gateways.
- [x] Async state is durable; outbox, idempotency, retries, DLQ, and trace IDs are covered.
- [x] Ownership checks, private defaults, protected assets, and safe logs are specified.
- [x] REST, SSE, messages, and AI outputs have versioned contracts and schema validation.
- [x] Tests precede implementation and cover dependency-failure/data-survival paths.
- [x] User-visible job status and operator observability are included without leaking infrastructure vocabulary.

## Design

1. **按用户解析并冻结能力**：把当前进程全局 MCP ToolDefinition 中的用户连接绑定移出全局注册表，改为按请求/用户解析。规划前持久化 `AgentCapabilitySnapshot` 与条目，只保存安全名、类型、职责、输入/输出 Schema、风险、权限、目录版本和私有 provider 映射引用。安全名限定为字母、数字、下划线和连字符且不超过 64 字符，稳定映射到远端原名，解决 Anthropic 工具名限制和多用户连接覆盖风险。
2. **LangGraph 固定安全元图**：LLM 只生成经过校验的 `agent-task-plan.v2` 数据，LangGraph 运行固定的 `orchestrate_task` 图，而不是动态编译任意代码。图节点为 `load_snapshot → validate_plan → dispatch_ready_steps → fan_in → mutation_preview → approval_interrupt → mutation_apply → verify → reconcile_report → finalize`；动态步骤由受控 dispatcher 使用 `Send` 映射到平台注册 operator。LangGraph 负责路由、并行、checkpoint、interrupt、恢复和节点重试；平台负责计划 Schema、能力、范围和写入安全校验。
3. **类型化产物与持久批次**：产物使用有界 `agent-step-artifact.v2` 信封，保存契约版本、摘要、对象范围、来源 digest、序号、项数和字节数；输出通过 Schema 后才释放图状态。固定 Graph 保持少量业务节点，operator 内按 50～100 项持久化批次和逐项 outcome，最多处理 1,000 项，并发默认 4；每批结果写入业务表和 checkpoint，不创建第二套 ready-step scheduler。
4. **可靠 Graph Run 派发**：graph start/resume 命令在业务状态事务内写入现有 Outbox，由发布器确认投递；周期扫描只做补偿。一个 Celery task 对应一次 Graph invoke/resume，LangGraph `thread_id=plan_id`，`checkpoint_id` 由运行时管理。尝试投递键与稳定业务 effect key 分离，broker 重投不会重复业务效果。
5. **冻结批量预览与异步写入**：扩展现有 `PendingWrite`，保存版本化预览、摘要 digest、来源产物 digest、过期时间和确认 digest；逐项 `AgentMutationItem` 保存对象、预期版本、建议分类、可信度、来源、风险和状态。图在 `approval_interrupt` 节点暂停，确认 API 只写入 resume command 并排队恢复 Graph，不在 HTTP 事务内调用慢 MCP。执行前重新校验快照绑定、实时授权、归属、版本和幂等账本；冲突逐项记录，禁止删除或覆盖回退。
6. **独立回读验证**：写工具仅把逐项结果标为 applied/unknown/conflict/failed。Graph 的 verify node 使用已授权读取能力检查实际分类；只有 intended 与 observed 一致才记为 verified。写请求超时且副作用不明确时先回读，不盲目重试；缺少验证能力时进入 manual review。
7. **可核对、可重建报告**：终态 reconciliation 服务从持久 mutation item、verification 和安全产物生成 `task-report.v1`，先校验各状态总数，再确定性渲染 Markdown。可选 LLM 只允许重组有界安全事实，不能修改统计；失败立即使用确定性版本。每次报告保存 source digest 和 revision；重新生成只读现有结果，不调用业务 MCP 或重复写入。
8. **紧凑实时 UI**：把公共计划视图和 `agent.plan_updated` 升级为 v2，增加 phase、活动步骤、对象统计、唯一 required action 和报告引用，SSE 不发送完整预览、正文、产物或 Markdown。Vue 页面显示一行实时状态、默认折叠步骤详情，确认表分页加载，报告 ready 后按需加载；只有 required action 改变才请求确认，展开执行记录时才加载历史，刷新以最新快照恢复。
9. **博客分类参考能力**：内部博客 MCP 保留现有搜索、文章读取和分类读取能力，增加受控的版本感知分类写入及对应验证能力。分类建议只能引用快照中读取到的启用分类；低可信度项进入人工复核。批量写逐项调用领域服务的乐观锁路径，不复用缺少 expected version 的旧批量分类入口。
10. **安全与可观测性**：MCP structured output 按快照 output Schema 校验并受大小限制；外部内容始终作为不可信数据，不得更改计划/权限。每个 snapshot、Graph thread/run/node、batch/item、attempt、preview、verification、report 和 Outbox event 传播 trace ID 与安全 digest；日志只记录稳定错误码、数量和脱敏业务 ID。

## Project Structure

### Documentation (this feature)

```text
specs/012-generic-mcp-orchestration/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/requirements.md
└── contracts/
    ├── agent-orchestration-api.md
    ├── capability-snapshot.v1.json
    ├── agent-task-plan.v2.json
    ├── agent-step-artifact.v2.json
    ├── mutation-preview.v2.json
    ├── verification-result.v1.json
    ├── task-report.v1.json
    └── agent-plan-event.v2.json
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/0024_generic_mcp_orchestration.py
├── app/models/agent.py
├── app/models/agent_conversation.py
├── app/modules/agent/
│   ├── capability_snapshot_service.py
│   ├── planning_schemas.py
│   ├── planning_service.py
│   ├── registry.py
│   ├── artifact_service.py
│   ├── graph_runtime.py
│   ├── mutation_service.py
│   ├── verification_service.py
│   ├── report_service.py
│   ├── graph_nodes.py
│   ├── graph_operators.py
│   ├── service.py
│   ├── status.py
│   ├── schemas.py
│   └── router.py
├── app/modules/blog_mcp/server.py
├── app/modules/posts/service.py
├── app/services/mcp/{base.py,gateway.py,provider.py}
├── app/services/outbox/publisher.py
├── app/workers/tasks/agent.py              # 只启动/恢复 Graph Run
├── app/workers/tasks/agent_graph.py        # LangGraph graph entrypoint
└── tests/{unit,contract,integration,reliability,security,performance}/

frontend/
├── src/api/{agentPlans.ts,agentReports.ts}
├── src/components/agent/
│   ├── AgentPlanCard.vue
│   ├── AgentPlanStep.vue
│   ├── AgentProgressStrip.vue
│   ├── MutationPreviewTable.vue
│   ├── ConfirmationCard.vue
│   └── TaskReportCard.vue
├── src/stores/agentConversations.ts
├── src/modules/agent/AgentPage.vue
└── tests/{component,e2e}/
```

**Structure Decision**: 在现有 Agent modular monolith 中以 LangGraph 作为唯一编排内核，复用现有 MCP 网关、PendingWrite、Outbox、Celery、Job/SSE 和 Vue 对话组件。`AgentExecutionPlan` 等表是用户/审计投影，LangGraph PostgreSQL Checkpoint 是运行时恢复状态；不保留第二套自研 scheduler，不增加服务或 worker 拓扑。

## Post-design Constitution Check

PASS。用户消息与能力快照先落库；LangGraph Graph State 通过 PostgreSQL Checkpoint 持久化并由 `thread_id=plan_id` 恢复；计划只引用快照且调用时重新授权；批量写入冻结预览、interrupt 确认、异步执行并逐项乐观锁；只有回读验证成功才进入报告成功数；Graph start/resume 通过事务 Outbox；REST、SSE、计划、产物、预览、验证和报告均有版本化契约；Vue 控制面不暴露基础设施和敏感信息。

## Complexity Tracking

无 Constitution 例外。引入 LangGraph 是为了复用成熟的 checkpoint、interrupt、Send 并行和节点恢复能力，替换现有自研 scheduler；新增能力快照、逐项 mutation/verification 和报告表仍是业务安全与审计需要，不能由编排框架替代。继续复用现有数据库、Outbox、队列和 UI，不新增 LangGraph Server 或外部编排服务。
