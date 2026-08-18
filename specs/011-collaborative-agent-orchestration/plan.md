# Implementation Plan: 对话式协作 Agent 调度

**Branch**: `011-collaborative-agent-orchestration` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/011-collaborative-agent-orchestration/spec.md`

## Summary

把当前“会话路由后同步执行一个工具/任务”的自助 Agent 改为持久化、可审计的计划执行器。任务消息先由版本化规划 Prompt 生成有界 DAG，经确定性权限、Schema、依赖和写确认校验后落库；调度器只把依赖已满足的步骤异步入队，步骤之间通过结构化持久产物传递范围和结果。每次状态转换写入可重放事件，前端在对应对话轮次内实时显示计划，终态首次到达时自动折叠并允许用户展开追溯。

## Technical Context

**Language/Version**: Python 3.12；TypeScript 5.7；Node 24

**Primary Dependencies**: FastAPI、SQLAlchemy/Alembic、Pydantic、Celery、PostgreSQL、Vue 3、Pinia、现有 SSE Job 流

**Storage**: PostgreSQL 新增执行计划、计划步骤、依赖、产物和尝试表；继续使用 `AgentTask`、`AgentRun`、`AsyncJobEvent`、`PendingWrite`

**Testing**: pytest 单元/契约/集成/可靠性/安全测试；Vitest 组件测试；Playwright Agent E2E

**Target Platform**: 现有 Docker Compose 单机部署，继续使用 worker-fast、worker-heavy 与 beat

**Project Type**: 前后端 Web 应用与异步工作进程

**Performance Goals**: 正常任务 2 秒内出现计划；状态转换 2 秒内可见；独立同耗时步骤比串行至少快 30%；每任务最多 12 个计划步骤，每用户每计划默认并发不超过 4

**Constraints**: 不增加 WebSocket、独立编排服务或递归 Agent；数据库是状态真相；写入确认、所有权、MCP 授权和工具 Schema 每次调用前重校验；事件不得包含 Prompt、推理、凭据或原始工具输出

**Scale/Scope**: 单用户个人服务器；活跃会话恢复最多返回最近 20 个计划，每计划最多 12 步，每个步骤最多 2 次执行尝试

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

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

1. 新增 `agent_task_plan` AI 配置模块与 `agent-task-plan.v1` 严格输出 Schema。模型只看到安全工具清单、当前授权范围和用户请求；平台根据工具确定 Agent 身份，模型不能授予权限或直接批准写入。
2. 新增 `AgentExecutionPlan`、`AgentPlanStep`、`AgentStepDependency`、`AgentStepArtifact`、`AgentStepAttempt`。计划先完整落库，再发布 `agent.plan_updated` 并调度；步骤与事件均使用单调递增版本抵抗乱序。
3. `execute_conversation_turn` 只负责快速回复、路由、规划和持久化，不再在同一调用里跑完整任务。协调任务领取计划锁，把依赖满足的步骤由 `pending` 原子转换为 `queued`；单步骤单独入队，同一 ready 集合的多个步骤在现有 `worker-heavy` 单槽位内使用有界线程池和隔离数据库 session 并行执行，不新增 worker 拓扑。
4. 每个步骤都有独立持久状态、执行尝试和事务。执行器在调用前重新检查计划所有权、工具可用性、MCP grant、参数 Schema、对象范围和写确认；完成后保存结构化产物并重新触发协调器。相同步骤通过状态锁和幂等键避免重复执行；内容分析步骤内部也按文章使用隔离 session 有界并发。
5. 首期提供工具级适配器：文章列表与分类查询直接生成产物；内容分析步骤可从前置文章列表产物或会话范围取得对象 ID，并复用现有有界文章分析；MCP 读工具保存安全结构化摘要；写工具创建 `PendingWrite` 并暂停依赖链。
6. 协调器在所有步骤终止后按持久产物确定性生成最终摘要，更新 `AgentTask`、`AgentTurn`、Job 与 Assistant Message。失败步骤只阻断依赖它的步骤，允许 `partial_success`。
7. 扩展现有 SSE 快照与事件：`agent.plan_updated` 携带有界完整计划视图；断线重连可从数据库恢复。继续使用 `/events/jobs`，不增加新长连接协议。
8. 前端新增按 `turn_id/user_message_id` 关联的计划 Store 与 `AgentPlanCard`。活动计划默认展开；首次终态事件自动折叠；用户手动状态在当前页面会话内优先。状态文字、图标与 `aria-live` 同时表达，不依赖颜色。
9. 旧 `/agent/tasks` 入口通过同一计划服务建立单步或多步计划并异步调度；现有任务详情、确认和执行记录 API 保持兼容。

## Project Structure

### Documentation (this feature)

```text
specs/011-collaborative-agent-orchestration/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── agent-plan-api.md
│   ├── agent-task-plan.v1.json
│   └── agent-plan-event.v1.json
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/
├── app/models/agent.py
├── app/modules/ai_config/catalog.py
├── app/modules/agent/
│   ├── conversation_service.py
│   ├── planning_schemas.py
│   ├── planning_service.py
│   ├── scheduler.py
│   ├── step_executor.py
│   ├── schemas.py
│   ├── status.py
│   └── router.py
├── app/modules/jobs/sse.py
└── app/workers/tasks/agent.py

backend/tests/
├── contract/
├── integration/
├── reliability/
├── security/
└── unit/

frontend/
├── src/api/agentPlans.ts
├── src/components/agent/
│   ├── AgentPlanCard.vue
│   ├── AgentPlanStep.vue
│   └── ConversationTimeline.vue
├── src/stores/agentConversations.ts
└── tests/{component,e2e}/
```

**Structure Decision**: 在现有 modular monolith 的 Agent 模块内增加计划、调度和步骤执行边界；复用当前 ToolRegistry、Celery、Job/SSE、PendingWrite 与对话模型，不引入新的服务或消息基础设施。

## Post-design Constitution Check

PASS。计划和步骤在调度前落库；模型只提出 DAG，平台负责授权与执行；每个写步骤仍由独立确认恢复；SSE、AI 输出和 REST 均有版本化契约；失败时消息、计划和已完成产物继续可见。

## Complexity Tracking

无 Constitution 例外。新增五张计划执行表是为了实现可恢复 DAG、逐步事件和安全重试；把这些状态塞入单个 JSON 字段会失去行级领取、依赖查询、唯一约束和可审计尝试，因此未采用。
