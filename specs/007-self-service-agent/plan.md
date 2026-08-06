# Implementation Plan: 自助式问答与任务执行 Agent

**Branch**: `006-agent-content-management`（feature.json 已 pin `specs/007-self-service-agent`，本特性不新建分支） | **Date**: 2026-08-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-self-service-agent/spec.md`

## Summary

为系统提供统一的自然语言入口：用户一句话提出查询、分析、批量处理或管理需求，系统识别意图、选择最少工具、按需取数、必要时并行处理，并把过程与结果如实呈现。

技术路径由 Phase 0 研究确定（详见 [research.md](./research.md)）：

- **状态通道复用**现有 `GET /events/jobs` SSE，新增 `agent.status_changed` 事件类型——该实现已具备 `Last-Event-ID` 重放、快照重同步、心跳与 DB 持久化事件源，无需重造（R-003）。
- **并行执行新建**：现有"多 Agent"实为单次 LLM 调用内的提示词角色组合，并非真并行（R-000）；且 `worker-heavy` 为 `-c 1` 单并发（R-001）。采用"单 Celery 任务内有界线程池扇出"，在不改动宪法约束的 worker 拓扑前提下获得真实并发。
- **确认走结构化端点**而非对话往返，复用现有 assistant action 的"重新校验归属 + 乐观版本 + 固定事件保护"模式（R-004）。
- **记录随 Job 生命周期级联清理**，不新增保留策略（R-006）。

## Technical Context

**Language/Version**: Python 3.12（后端）、TypeScript 5 + Vue 3（前端）

**Primary Dependencies**: FastAPI、SQLAlchemy 2、Alembic、Pydantic v2、Celery、Naive UI；LLM 经 `app/services/llm/gateway.py` 类型化网关

**Storage**: PostgreSQL（任务、运行实例、执行记录、待确认写操作、SSE 事件）；Redis（唤醒提示与锁，非事实源）；RabbitMQ（命令与事件）

**Testing**: pytest（`backend/tests/` 下 `unit` / `contract` / `integration` / `security` 分层，已有约定）；前端 Vitest + Playwright

**Target Platform**: Linux 服务器，Docker Compose 单机自托管

**Project Type**: Web application（`backend/` + `frontend/` 双目录，模块化单体）

**Performance Goals**: 首个状态事件 ≤ 2s（SC-002）；25 对象批量任务并行相较串行耗时下降 ≥ 50%（SC-010，依赖线程池扇出落地）

**Constraints**: `worker-heavy` 单并发槽位与 voice/image/maintenance 共享，Agent 并发默认 4、上限 8（R-005）；单批对象默认 200、上限 500；`AsyncJobEvent.event_type` 限长 40 字符

**Scale/Scope**: 个人自托管单用户；预计新增 4 张表、1 组 REST 端点、1 个 SSE 事件类型、1 个 Celery 任务族，并重构现有 `assistant` 模块

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution version**: 1.1.0（本特性触发了 1.0.0 → 1.1.0 修订，解除 MCP 延后并新增 Agent 工具调用条款）

### Pre-Phase 0（初评）

- [x] User content is durably persisted before AI or other long-running work starts.
      — AI 产出（标签、关键词、改写）在确认前仅为 `PendingWrite` 提案，不进业务状态；任务与记录在任务创建时即落库，不依赖 LLM 成功。
- [x] AI mutations are previewed/confirmed, reversible, and never move fixed events.
      — FR-021~024；确认走结构化端点（R-004），写入复用既有领域服务，固定事件保护由 `calendar_service` 既有校验承担（FR-050）。
- [x] Design remains a modular monolith deployable through Docker Compose.
      — 新增模块位于 `backend/app/modules/agent/`，无新增服务进程；worker 拓扑不变（R-001 方案 C）。
- [x] AI, speech, mail, and storage integrations use provider-neutral gateways.
      — LLM 经既有 `llm/gateway.py`；工具调用经新建的类型化工具注册表（宪法 1.1.0 新增条款，FR-041）。
- [x] Async state is durable; outbox, idempotency, retries, DLQ, and trace IDs are covered.
      — 状态事实源为 PostgreSQL；沿用既有 outbox 与 `llm` 队列的 DLQ 路由；重试为有界一次（FR-033）。
- [x] Ownership checks, private defaults, protected assets, and safe logs are specified.
      — FR-043 强制归属；FR-042 禁止凭据进入提示词/事件/记录；FR-031 参数脱敏。
- [x] REST, SSE, messages, and AI outputs have versioned contracts and schema validation.
      — Phase 1 产出 `contracts/openapi.yaml` 与 `agent-status-event.v1.json`；LLM 结构化输出经 `gateway.structured()` 校验。
- [x] Tests precede implementation and cover dependency-failure/data-survival paths.
      — 见下方"测试策略"；含 LLM 不可用、部分失败、未确认不写入三类。
- [x] User-visible job status and operator observability are included without leaking infrastructure vocabulary.
      — 状态事件面向用户语义（Agent 名称/职责/进度），FR-028 禁止暴露内部推理与提示词；不出现 Celery/RabbitMQ 词汇。

**Gate result: PASS**（无违规，Complexity Tracking 留空）

### Post-Phase 1（复评）

- [x] 全部 9 项复评通过。Phase 1 设计未引入新的宪法偏离：
  - 未新增服务进程或 worker 队列（方案 C 在既有 `llm` 队列内执行）。
  - 未新增第二条实时通道（复用 `/events/jobs`）。
  - 未新增第二套数据保留语义（随 Job 级联，R-006）。
  - 新增的工具注册表满足 1.1.0 新条款：只暴露安全清单字段、强制归属、脱敏审计、未注册工具不可调用。

**Gate result: PASS**

## Project Structure

### Documentation (this feature)

```text
specs/007-self-service-agent/
├── plan.md              # 本文件
├── research.md          # Phase 0 输出：4 项澄清决策 + 3 项事实修正
├── data-model.md        # Phase 1 输出
├── quickstart.md        # Phase 1 输出
├── contracts/           # Phase 1 输出
│   ├── openapi.yaml
│   └── schemas/
│       ├── agent-status-event.v1.json
│       └── agent-tool-manifest.v1.json
└── tasks.md             # Phase 2 输出（/speckit-tasks，不由本命令创建）
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── modules/
│   │   ├── agent/                  # 新增：本特性主模块
│   │   │   ├── __init__.py
│   │   │   ├── router.py           # REST：任务创建/查询/确认
│   │   │   ├── service.py          # 任务生命周期、范围解析、汇总
│   │   │   ├── schemas.py          # Pydantic 契约
│   │   │   ├── intents.py          # 可扩展意图注册（FR-048 去硬编码）
│   │   │   ├── registry.py         # 类型化工具注册表（宪法 1.1.0）
│   │   │   ├── runner.py           # 有界线程池扇出执行器（R-001 方案 C）
│   │   │   ├── status.py           # agent.status_changed 事件构造与发布
│   │   │   └── audit.py            # ExecutionRecord 写入与脱敏
│   │   ├── assistant/              # 重构：吸收进 agent 模块，保留兼容层（FR-051）
│   │   ├── jobs/
│   │   │   └── sse.py              # 修改：快照负载扩展（R-003 Consequences）
│   │   └── posts/
│   │       └── orchestrator.py     # 复用：选择/门控逻辑（不复用其提示词组合）
│   ├── models/
│   │   └── agent.py                # 新增：AgentTask/AgentRun/ExecutionRecord/PendingWrite
│   └── workers/tasks/
│       └── agent.py                # 新增：Celery 任务族，路由至既有 llm 队列
├── alembic/versions/
│   └── 0019_agent_runtime.py       # 新增迁移（当前最新为 0018）
└── tests/
    ├── contract/test_agent_contracts.py
    ├── integration/test_agent_runtime.py
    ├── security/test_agent_ownership_and_redaction.py
    └── unit/test_agent_intents.py

frontend/
└── src/
    ├── components/agent/           # Agent 状态面板
    ├── pages/                      # 自然语言入口
    └── services/                   # /events/jobs 事件分流
```

**Structure Decision**: 沿用既有 `backend/app/modules/<domain>/` 模块化单体布局，新增 `agent` 模块承载运行期职责。Agent 的**定义**不落在此处——按 spec D-002，配置权威源是 006 的博客 Agent 管理，本模块只消费其生效版本。现有 `assistant` 模块按 D-003 吸收重构，其对外三个端点保留兼容层。

## 测试策略（Constitution VII：测试先行）

| 层 | 覆盖 | 关键用例 |
|---|---|---|
| contract | REST + SSE 事件 + 工具清单 schema | `agent.status_changed` 字段完整性与 `status` 枚举约束；`event_type` ≤ 40 字符 |
| integration | 任务全生命周期、并行扇出、部分失败 | 25 对象批量中 5 项失败 → 已成功项保留、终态为 `partial_success`；LLM 网关不可用 → 原有数据完好且任务可重试 |
| security | 归属、脱敏、未确认不写入 | 跨用户访问任务返回 404；执行记录全文无凭据模式；未确认状态下写接口零调用 |
| unit | 意图注册、范围解析、数据整理 | 新增意图无需改调度代码（FR-048）；"这些"解析为上一轮 ID 集合（FR-035） |

**数据存活验证**（Constitution VII 强制）：LLM 与消息代理不可用时，用户文章保持可访问，已完成步骤结果保留，任务转 `partial_success` 而非整体回滚，且不以模拟数据填充。

## Complexity Tracking

> Constitution Check 无违规，本表留空。

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| （无） | — | — |

## 已知风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 线程池扇出占满 `worker-heavy` 唯一槽位，饿死语音/图片处理 | 既有功能延迟 | 并发默认 4、上限 8（R-005）；单批 200 上限；后续可观测队列等待时长 |
| `assistant` 重构破坏既有前端调用 | 现有功能回归 | FR-051 要求兼容层；契约测试覆盖三个既有端点 |
| SSE 快照未扩展导致重连后 Agent 面板空白 | 体验缺陷 | R-003 已列为必做工作量，contract 测试覆盖 |
| `ExecutionRecord` 误建业务实体外键 | 清空任务历史连带删除业务数据 | data-model 硬约束 + 专项测试（R-006 Consequences） |
