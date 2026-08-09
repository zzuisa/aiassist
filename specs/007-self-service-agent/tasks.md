---

description: "Task list template for feature implementation"
---

# Tasks: 自助式问答与任务执行 Agent

**Input**: Design documents from `/specs/007-self-service-agent/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are REQUIRED (Constitution VII). Place unit, contract, integration, and critical failure-path tests before the implementation tasks they validate.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Web app（模块化单体）：`backend/app/`、`backend/tests/`、`frontend/src/`。路径取自 plan.md 的 Structure Decision 与仓库现状。

## 本特性的四条硬约束（贯穿全部任务）

1. **记录表禁止对业务实体建外键**（data-model 硬约束 2 / R-006）：`clear_completed_jobs()` 级联删除时会连带删除用户文章。由 T007 落实、T020 与 T101 专项验证。
2. **凭据禁止进入提示词、状态事件、执行记录**（宪法 1.1.0 / FR-042）：脱敏在写入前强制执行，由 T013 落实、T019 与 T039 专项验证。
3. **Agent 定义来自 spec 006，本特性不自建**（D-002 / FR-045）：运行实例只存绑定版本快照。
4. **并发受限于 `worker-heavy` 单槽位**（R-001）：线程池扇出，默认 4、上限 8，不得饿死语音/图片处理。

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 模块骨架与配置项就位

- [X] T001 创建 `backend/app/modules/agent/__init__.py` 模块骨架目录
- [X] T002 [P] 在 `backend/app/core/config.py` 新增 `AGENT_MAX_BATCH_OBJECTS`（默认 200，上限 500）与 `AGENT_MAX_CONCURRENCY`（默认 4，上限 8）配置项，值域校验写在 Settings 内
- [X] T003 [P] 在 `.env.example` 补充上述两个配置项及注释说明其与 `worker-heavy` 单并发的关系
- [X] T004 [P] 在 `backend/app/workers/celery_app.py` 的 `task_routes` 增加 `app.workers.tasks.agent.*` → `llm` 队列路由（复用既有队列，不新增）

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 所有用户故事共同依赖的核心设施

**⚠️ CRITICAL**: 本阶段完成前，任何用户故事不得开工

### 数据层

- [X] T005 在 `backend/app/models/agent.py` 定义 `AgentTask` 模型（`job_id` UNIQUE NOT NULL FK → `async_jobs.id` ON DELETE CASCADE，见 R-002）
- [X] T006 在 `backend/app/models/agent.py` 定义 `AgentRun` 模型（含 `agent_key`/`agent_version`/`allow_write` 默认 false/`progress_current`/`progress_total`/`stage_label`）（FR-014 的 9 个必备字段）
- [X] T007 在 `backend/app/models/agent.py` 定义 `ExecutionRecord` 模型 —— **禁止对任何业务实体建外键**，被操作对象以 UUID 值记录在 `params_digest_json`
- [X] T008 在 `backend/app/models/agent.py` 定义 `PendingWrite` 模型（`decision` 默认 `pending`，`targets_json` 含目标 ID 与乐观版本号）
- [X] T009 在 `backend/app/models/__init__.py` 导出上述四个模型
- [X] T010 创建迁移 `backend/alembic/versions/0019_agent_runtime.py`，建四张表及 data-model.md 指定的全部索引（当前最新版本为 `0018`）

### 基础设施

- [X] T011 [P] 在 `backend/app/modules/agent/intents.py` 实现可扩展意图注册表：装饰器或注册函数登记 `intent_key` → handler，**禁止 if/elif 硬编码分支**（FR-001/FR-048）
- [X] T012 [P] 在 `backend/app/modules/agent/registry.py` 实现类型化工具注册表：只暴露 `agent-tool-manifest.v1.json` 允许的安全清单字段，未注册工具调用抛领域错误（FR-041/FR-044）
- [X] T013 [P] 在 `backend/app/modules/agent/audit.py` 实现 `ExecutionRecord` 写入器，含脱敏函数（键名匹配 password/token/secret/api_key/cookie/authorization/private_key 及其连字符变体，值匹配 `eyJ` 前缀与 `Bearer ` 前缀 → `[redacted]`）
- [X] T014 [P] 在 `backend/app/modules/agent/service.py` 实现任务生命周期：创建 `AgentTask` + 配对 `AsyncJob` 于同一事务，**在任何模型调用之前提交**（Constitution I）
- [X] T015 在 `backend/app/modules/agent/schemas.py` 按 `contracts/openapi.yaml` 定义全部 Pydantic 模型（`AgentTask`/`AgentTaskDetail`/`AgentRun`/`Progress`/`ExecutionRecord`/`PendingWrite`/`ToolManifestEntry`）
- [X] T016 在 `backend/app/modules/agent/router.py` 注册 `/agent` 路由并挂载到 `backend/app/main.py`，写方法依赖 `require_csrf`
- [X] T017 在 `backend/app/workers/tasks/agent.py` 创建 Celery 任务族骨架（路由至既有 `llm` 队列，不新增 worker）

### 基础测试

- [X] T018 [P] 单元测试 `backend/tests/unit/test_agent_intents.py`：新增意图无需修改调度代码即可被识别（FR-048）
- [X] T019 [P] 安全测试 `backend/tests/security/test_agent_redaction.py`：含各类凭据的参数经脱敏后写入，记录全文无凭据（FR-031/FR-042/SC-006）
- [X] T020 [P] 集成测试 `backend/tests/integration/test_agent_cascade.py`：`clear_completed_jobs()` 后 Agent 四表级联清空，**且 posts 表记录数不变**（硬约束 1）

**Checkpoint**: 基础设施就绪 —— 用户故事可以开工

---

## Phase 3: User Story 1 - 自然语言查询，只拿必要数据 (Priority: P1) 🎯 MVP

**Goal**: 用户一句话查询，系统识别意图、调只读接口、只返回轻量字段，不读正文

**Independent Test**: 提出"给我最近 10 篇文章"，返回 10 条含标题与链接的结果；执行记录中不存在正文读取条目

### Tests for User Story 1 (REQUIRED; write first) ⚠️

> **NOTE: 先写测试并确认其失败，再写实现**

- [X] T021 [P] [US1] 契约测试 `backend/tests/contract/test_agent_task_contract.py`：`POST /agent/tasks` 返回 202 与 `AgentTask` schema，`GET /agent/tasks/{id}` 返回 `AgentTaskDetail`
- [X] T022 [P] [US1] 集成测试 `backend/tests/integration/test_agent_query_minimal.py`：查询任务完成后执行记录中**无** `operation_type=analyze` 条目，返回字段不含正文（SC-001/FR-009）
- [X] T023 [P] [US1] 集成测试 `backend/tests/integration/test_agent_aggregate.py`：分类统计走聚合接口，不逐篇拉取（FR-011）
- [X] T024 [P] [US1] 单元测试 `backend/tests/unit/test_agent_data_cleaning.py`：去空值、去重、名称格式统一、异常标记（FR-018）
- [X] T025 [P] [US1] 安全测试 `backend/tests/security/test_agent_ownership.py`：跨用户访问他人任务返回 404（FR-043）

### Implementation for User Story 1

- [X] T026 [US1] 在 `backend/app/modules/agent/registry.py` 登记只读查询工具（文章列表检索、分类/标签统计、时间线），复用既有 `/blog/search`、`/blog/taxonomy` 等服务层函数，`type=read`
- [X] T027 [US1] 在 `backend/app/modules/agent/intents.py` 注册查询类意图 handler：文章列表、分类统计、标签检索
- [X] T028 [US1] 在 `backend/app/modules/agent/service.py` 实现澄清提问判定：需求可由上下文确定时不追问；仅当关键条件缺失且无法从工具或上下文获得时提问，且只问必要项（FR-002/FR-003）
- [X] T029 [US1] 在 `backend/app/modules/agent/service.py` 实现工具选择：最少工具组合，禁止调用无关接口、禁止重复取数（FR-004/FR-005）
- [X] T030 [US1] 在 `backend/app/modules/agent/service.py` 实现字段裁剪，列表类请求只返回 data-model 允许的轻量字段（FR-008）
- [X] T031 [US1] 在 `backend/app/modules/agent/service.py` 实现结果整理：去空、去重、格式统一、异常标记（FR-018/FR-019）
- [X] T032 [US1] 在 `backend/app/modules/agent/service.py` 实现查询类回复组装：处理结果 / 执行记录 / 局限说明三段结构，且不输出正文、数据库字段、完整接口响应或工具内部参数（FR-038/FR-040/FR-020）
- [X] T033 [US1] 在 `backend/app/modules/agent/router.py` 实现 `POST /agent/tasks`、`GET /agent/tasks`、`GET /agent/tasks/{task_id}`
- [X] T034 [US1] 在 `backend/app/workers/tasks/agent.py` 实现查询任务执行体，逐步写 `ExecutionRecord`
- [X] T035 [P] [US1] 前端 `frontend/src/api/agent.ts` 封装上述三个端点
- [X] T036 [US1] 前端 `frontend/src/modules/agent/AgentPage.vue` 自然语言输入框与轻量结果列表（标题、链接、标签）

**Checkpoint**: US1 独立可用 —— 自然语言查询已可交付

---

## Phase 4: User Story 2 - 实时看见谁在干什么 (Priority: P1)

**Goal**: 执行期间前端持续看到 Agent 名称、职责、当前任务、工具、状态、进度

**Independent Test**: 触发任意查询并订阅 `/events/jobs`，收到至少一次 `running` 与一次终态事件，字段完整

### Tests for User Story 2 (REQUIRED; write first) ⚠️

- [X] T037 [P] [US2] 契约测试 `backend/tests/contract/test_agent_status_event.py`：事件负载符合 `agent-status-event.v1.json`，`status` 落在七值枚举，`event_type` 字符串 ≤ 40 字符（`async_job_events.event_type` 限长）（FR-025/FR-026）
- [X] T038 [P] [US2] 集成测试 `backend/tests/integration/test_agent_sse.py`：任务全程事件序列完整；重连带 `Last-Event-ID` 不丢事件；游标失效时快照含在跑的 Agent
- [X] T039 [P] [US2] 安全测试 `backend/tests/security/test_agent_event_leakage.py`：事件中无系统提示词、无模型推理、无凭据（FR-028）
- [X] T040 [P] [US2] 单元测试 `backend/tests/unit/test_agent_progress.py`：总量不可知时 `progress` 为 null 且 `stage_label` 有值，**不伪造进度数字**（FR-027）

### Implementation for User Story 2

- [X] T041 [US2] 在 `backend/app/modules/agent/status.py` 实现 `agent.status_changed` 事件构造与发布，**与业务变更同事务**写入 `async_job_events`（沿用既有约定）
- [X] T042 [US2] 在 `backend/app/modules/agent/service.py` 的 Agent 生命周期各转换点接入状态发布
- [X] T043 [US2] 扩展 `backend/app/modules/jobs/sse.py` 的 `_snapshot_payload()`，加入当前在跑的 Agent 运行实例，避免重连后面板空白（R-003 唯一新增工作量）
- [X] T044 [P] [US2] 前端 `frontend/src/stores/agent.ts` 在既有 `/events/jobs` 连接上按 `event_type` 分流 `agent.status_changed`（参考 `frontend/src/stores/jobs.ts:138` 的 addEventListener 模式）
- [X] T045 [US2] 前端 `frontend/src/components/agent/AgentStatusPanel.vue` 展示名称、职责、当前任务、工具、状态、进度；多 Agent 并行时各自独立呈现

**Checkpoint**: US1 与 US2 均独立可用

---

## Phase 5: User Story 3 - 按需读正文，批量任务并行处理 (Priority: P2)

**Goal**: 分析类请求才读正文且只读目标；数量大时并行处理并汇总

**Independent Test**: 对上一步 10 篇提取标签，验证只读这 10 篇正文、多 Agent 并行、结果去重且区分四种状态

### Tests for User Story 3 (REQUIRED; write first) ⚠️

- [X] T046 [P] [US3] 集成测试 `backend/tests/integration/test_agent_body_on_demand.py`：分析类请求读正文、列表类请求不读（FR-010/FR-002）
- [X] T047 [P] [US3] 集成测试 `backend/tests/integration/test_agent_parallel.py`：多 `AgentRun` 的 `input_scope` 互不重叠（FR-015）；25 对象任务并行相较串行耗时下降 ≥ 50%（SC-010）
- [X] T048 [P] [US3] 集成测试 `backend/tests/integration/test_agent_partial_failure.py`：5/25 失败时已成功项保留、终态 `partial_success`、失败项与原因单列（FR-034/SC-008）
- [X] T049 [P] [US3] 集成测试 `backend/tests/integration/test_agent_llm_unavailable.py`：LLM 网关不可用时用户文章完好可访问、任务可重试、**不以模拟数据填充**（Constitution VII 数据存活）
- [X] T050 [P] [US3] 单元测试 `backend/tests/unit/test_agent_batch_limits.py`：超过 `AGENT_MAX_BATCH_OBJECTS` 时说明实际处理范围并要求收窄

### Implementation for User Story 3

- [X] T051 [US3] 在 `backend/app/modules/agent/runner.py` 实现有界线程池扇出执行器（并发取自 `AGENT_MAX_CONCURRENCY`，运行在单个 Celery 任务内，见 R-001 方案 C）
- [X] T052 [US3] 在 `backend/app/modules/agent/service.py` 复用 `backend/app/modules/posts/orchestrator.py` 的**选择与门控逻辑**（价值评分、能力可用性、跳过原因码）—— 不复用其提示词组合方式（R-000）（FR-017）
- [X] T053 [US3] 在 `backend/app/modules/agent/service.py` 实现单/多 Agent 判定：单接口可完成或数据量小时用单 Agent（FR-012/FR-013）
- [X] T054 [US3] 在 `backend/app/modules/agent/service.py` 实现子 Agent 创建，绑定 spec 006 的当时生效版本至 `agent_version`（FR-014/FR-045/FR-046）
- [X] T055 [US3] 在 `backend/app/modules/agent/registry.py` 登记正文读取与内容分析工具
- [X] T056 [US3] 在 `backend/app/modules/agent/service.py` 实现主控汇总：去重、格式统一、质量检查、区分已生成未保存/已保存/失败/未处理（FR-016/FR-006）
- [X] T057 [US3] 在 `backend/app/modules/agent/service.py` 实现任务执行类回复组装：执行计划 / 当前运行 Agent / 执行结果 / 执行记录 四段结构（FR-039）
- [X] T058 [US3] 在 `backend/app/modules/agent/runner.py` 实现失败隔离：判定失败类型、安全时重试一次、失败不影响其他独立 Agent（FR-032/FR-033）

**Checkpoint**: US1–US3 均独立可用

---

## Phase 6: User Story 4 - 写操作先说清楚再动手 (Priority: P2)

**Goal**: 写入前说明影响范围并等待结构化确认，确认后经既有领域服务写入

**Independent Test**: 批量标签生成后要求保存，验证进入 `waiting_confirmation` 且零写入；确认后才写并返回明细

### Tests for User Story 4 (REQUIRED; write first) ⚠️

- [X] T059 [P] [US4] 契约测试 `backend/tests/contract/test_agent_confirmation.py`：`GET/POST /agent/tasks/{id}/confirmations[/{cid}]` 符合 `PendingWrite` schema
- [X] T060 [P] [US4] 安全测试 `backend/tests/security/test_agent_no_write_before_approval.py`：`decision != approved` 时目标对象零变化（SC-004/FR-022）
- [X] T061 [P] [US4] 集成测试 `backend/tests/integration/test_agent_write_apply.py`：批准后经既有领域服务写入，归属与乐观版本重校验；版本不匹配返回冲突而非静默覆盖（FR-024）
- [X] T062 [P] [US4] 集成测试 `backend/tests/integration/test_agent_high_risk.py`：删除/覆盖/批量更新即便原始请求已表达执行意图仍需二次确认（FR-023）
- [X] T063 [P] [US4] 集成测试 `backend/tests/integration/test_agent_no_write_capability.py`：只有读能力时明确说明"可生成但无法写回"，**不谎称已保存**（FR-006 写操作分支）

### Implementation for User Story 4

- [X] T064 [US4] 在 `backend/app/modules/agent/service.py` 实现 `PendingWrite` 生成：影响条数、修改范围、可回滚性、变更预览、`high_risk` 判定（FR-021）
- [X] T065 [US4] 在 `backend/app/modules/agent/service.py` 实现 `waiting_confirmation` 状态转换与恢复执行
- [X] T066 [US4] 在 `backend/app/modules/agent/router.py` 实现 `GET /agent/tasks/{id}/confirmations` 与 `POST .../confirmations/{cid}`
- [X] T067 [US4] 在 `backend/app/modules/agent/service.py` 实现批准后写入路径，全部经既有领域服务（不绕过归属、乐观版本、固定事件保护）
- [X] T068 [US4] 在 `backend/app/modules/agent/registry.py` 登记写入类工具，标记 `type=write` 并要求 `allow_write=true` 的 run + 已批准 `PendingWrite`
- [X] T069 [P] [US4] 前端 `frontend/src/components/agent/ConfirmationCard.vue` 渲染影响范围预览与批准/拒绝动作

**Checkpoint**: US1–US4 均独立可用

---

## Phase 7: User Story 5 - 每一步都留痕且可审计 (Priority: P3)

**Goal**: 维护者可查看任一任务的完整执行记录，且记录中无凭据

**Independent Test**: 执行含失败步骤的批量任务后导出记录，验证每次调用一条、字段完整、全文无凭据

### Tests for User Story 5 (REQUIRED; write first) ⚠️

- [ ] T070 [P] [US5] 契约测试 `backend/tests/contract/test_agent_records_contract.py`：`GET /agent/tasks/{id}/records` 符合 `ExecutionRecord` schema，`operation_type` 落在七值枚举（FR-030）
- [ ] T071 [P] [US5] 集成测试 `backend/tests/integration/test_agent_record_completeness.py`：多步骤任务的记录可按序还原，无步骤缺失，可区分成功/失败/跳过（SC-005）

### Implementation for User Story 5

- [ ] T072 [US5] 在 `backend/app/modules/agent/router.py` 实现 `GET /agent/tasks/{task_id}/records`
- [ ] T073 [US5] 在 `backend/app/modules/agent/audit.py` 补齐耗时统计与步骤序号，确保每次工具/子 Agent 调用均有独立条目（FR-029）
- [ ] T074 [P] [US5] 前端 `frontend/src/components/agent/ExecutionRecordList.vue` 按序展示执行记录

**Checkpoint**: US1–US5 均独立可用

---

## Phase 8: User Story 6 - 多轮对话里"这些"指的是刚才那些 (Priority: P3)

**Goal**: 指代解析到上一轮对象集合，不扩大到全量

**Independent Test**: 连续两轮，第二轮用指代词，处理对象集合与第一轮返回完全一致

### Tests for User Story 6 (REQUIRED; write first) ⚠️

- [ ] T075 [P] [US6] 集成测试 `backend/tests/integration/test_agent_scope_inheritance.py`：`previous_task_id` 传入后指代解析为上轮 ID 集合，未扩大到全库（SC-009/FR-035）
- [ ] T076 [P] [US6] 集成测试 `backend/tests/integration/test_agent_scope_staleness.py`：上轮对象已变更或删除时重新查询并向用户说明（FR-036）
- [ ] T077 [P] [US6] 单元测试 `backend/tests/unit/test_agent_scope.py`：已成功完成的步骤不重复执行（FR-037）

### Implementation for User Story 6

- [ ] T078 [US6] 在 `backend/app/modules/agent/service.py` 实现 `ConversationScope` 读写：上轮对象 ID、查询条件、范围、排序、已确认操作、未执行写操作、已完成与已失败对象，持久化至 `agent_tasks.scope_json`
- [ ] T079 [US6] 在 `backend/app/modules/agent/service.py` 实现范围有效性检测与失效重查
- [ ] T080 [US6] 在 `backend/app/modules/agent/router.py` 的 `POST /agent/tasks` 支持 `previous_task_id` 并校验其归属

**Checkpoint**: US1–US6 均独立可用

---

## Phase 9: User Story 7 - 做不到就说做不到 (Priority: P3)

**Goal**: 能力不足时输出结构化缺口说明，绝不编造

**Independent Test**: 提出系统确实不具备对应接口的请求，验证拒绝编造并给出可完成/不可完成划分

### Tests for User Story 7 (REQUIRED; write first) ⚠️

- [ ] T081 [P] [US7] 契约测试 `backend/tests/contract/test_agent_tools_manifest.py`：`GET /agent/tools` 符合 `agent-tool-manifest.v1.json`，**不含端点与凭据字段**（FR-042）
- [ ] T082 [P] [US7] 集成测试 `backend/tests/integration/test_agent_capability_gap.py`：无匹配工具时输出缺失能力/缺失接口或权限/可完成部分/不可完成部分/建议补充项（FR-007/SC-007）
- [ ] T083 [P] [US7] 集成测试 `backend/tests/integration/test_agent_no_fabrication.py`：未注册工具不被声称可调用，失败不以模拟数据代替（FR-006/FR-044）
- [ ] T084 [P] [US7] 集成测试 `backend/tests/integration/test_agent_unavailable_agent.py`：spec 006 中标记停用/未注册的 Agent 触发缺口说明而非伪执行（FR-047）

### Implementation for User Story 7

- [ ] T085 [US7] 在 `backend/app/modules/agent/service.py` 实现能力缺口分析与结构化输出
- [ ] T086 [US7] 在 `backend/app/modules/agent/router.py` 实现 `GET /agent/tools`
- [ ] T087 [US7] 在 `backend/app/modules/agent/registry.py` 实现 006 Agent/能力可用性检查，不可用时携带 `unavailable_reason`
- [ ] T088 [P] [US7] 前端 `frontend/src/components/agent/CapabilityGapNotice.vue` 展示能力缺口说明

**Checkpoint**: 全部用户故事独立可用

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: 跨故事的收尾与既有功能保护

### assistant 模块吸收（D-003 / FR-050 / FR-051）

- [ ] T089 契约测试 `backend/tests/contract/test_assistant_compat.py`：`POST /assistant/runs`、`GET /assistant/runs/{id}`、`POST /assistant/runs/{id}/actions/{action_id}` 三个既有端点行为不变
- [ ] T090 集成测试 `backend/tests/integration/test_assistant_migrated.py`：`plan_today` 与 `adjust_week` 作为普通意图继续可用，动作卡片仍引用真实实体 ID 与版本，固定事件不被 AI 移动（FR-050）
- [ ] T091 将 `plan_today` / `adjust_week` 注册为 `backend/app/modules/agent/intents.py` 中的普通意图，移除 `backend/app/modules/assistant/service.py` 的硬编码分支
- [ ] T092 移除 `backend/app/modules/assistant/service.py` 的进程内存 run 存储 `_RUNS`，改用持久化任务（FR-049）
- [ ] T093 在 `backend/app/modules/assistant/router.py` 保留兼容层，将既有三个端点代理至新体系（FR-051）

### 跨切面验证

- [ ] T094 [P] 集成测试 `backend/tests/integration/test_agent_restart_recovery.py`：进程重启后任务、状态与执行记录仍可查询（FR-049）
- [ ] T095 [P] 性能验证：并发扇出运行期间语音转写与图片处理不被饿死（`worker-heavy` 单槽位风险，plan.md 已知风险 1）
- [ ] T096 [P] 在 `backend/tests/integration/test_agent_latency.py` 验证首个状态事件延迟 ≤ 2s（SC-002）
- [ ] T097 [P] 在 `backend/tests/integration/test_agent_single_agent_ratio.py` 验证简单查询的单 Agent 占比 ≥ 95%（SC-003）
- [ ] T098 [P] 在 `backend/app/core/observability.py` 确认 trace id 贯穿 REST → Celery → LLM 网关 → 状态事件（Constitution VIII）
- [ ] T099 前端 `frontend/src/router/` 注册 Agent 页面路由并接入 `AppShell.vue` 导航
- [ ] T100 [P] 文档：在 `docs/operations.md` 补充两个新配置项的调优说明与单槽位并发注意事项
- [ ] T101 按 `specs/007-self-service-agent/quickstart.md` 逐节执行验收（9 节全过）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，可立即开始
- **Foundational (Phase 2)**: 依赖 Setup —— **阻塞全部用户故事**
- **User Stories (Phase 3–9)**: 均依赖 Phase 2 完成
- **Polish (Phase 10)**: 依赖所需故事完成；其中 assistant 吸收组（T089–T093）依赖 US1 与 US6

### User Story Dependencies

- **US1 (P1)**: Phase 2 后即可开始，无跨故事依赖 🎯 MVP
- **US2 (P1)**: Phase 2 后即可开始。US1 通过 REST 轮询已可独立验收，US2 增量补上实时推送
- **US3 (P2)**: Phase 2 后即可开始；与 US1 集成更完整但可独立验收
- **US4 (P2)**: 依赖 US3 产出待写入结果才有完整意义，但确认机制本身可用桩数据独立验收
- **US5 (P3)**: Phase 2 的审计写入器已就位，本阶段只加读取端点，可独立验收
- **US6 (P3)**: Phase 2 后即可开始，可独立验收
- **US7 (P3)**: Phase 2 后即可开始，可独立验收

### Within Each User Story

- 测试必须先写并确认失败，再写实现
- 模型 → 服务 → 端点 → 集成
- 故事完成后再进入下一优先级

### Parallel Opportunities

- Phase 1 中 T002/T003/T004 可并行
- Phase 2 中 T011–T014 可并行（不同文件），T018–T020 可并行
- Phase 2 完成后，US1–US7 可由不同人并行推进
- 各故事内标 [P] 的测试可并行编写
- Phase 10 中 T094–T098、T100 可并行

---

## Parallel Example: User Story 1

```bash
# 先并行写测试（确认全部失败）：
Task: "契约测试 backend/tests/contract/test_agent_task_contract.py"
Task: "集成测试 backend/tests/integration/test_agent_query_minimal.py"
Task: "集成测试 backend/tests/integration/test_agent_aggregate.py"
Task: "单元测试 backend/tests/unit/test_agent_data_cleaning.py"
Task: "安全测试 backend/tests/security/test_agent_ownership.py"

# 再并行推进前后端：
Task: "前端 frontend/src/api/agent.ts 封装端点"
Task: "后端 backend/app/modules/agent/registry.py 登记只读工具"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1: Setup
2. 完成 Phase 2: Foundational（**关键，阻塞全部故事**）
3. 完成 Phase 3: User Story 1
4. **停下来验证**：独立验收 US1 —— 自然语言查询可用且不读正文
5. 就绪即可部署演示

### Incremental Delivery

1. Setup + Foundational → 地基就绪
2. 加 US1 → 独立验收 → 部署（MVP：自然语言查询）
3. 加 US2 → 独立验收 → 部署（实时状态可见）
4. 加 US3 → 独立验收 → 部署（批量并行处理）
5. 加 US4 → 独立验收 → 部署（写操作闭环）
6. 加 US5/US6/US7 → 各自独立验收 → 部署
7. Phase 10 收尾，重点是 assistant 吸收不破坏既有前端

### Parallel Team Strategy

Phase 2 完成后可分工：US1+US2 一人（前端联动紧密）、US3+US4 一人（执行与写入链路）、US5+US6+US7 一人（记录、上下文、能力边界）。

---

## Notes

- [P] = 不同文件、无依赖，可并行
- [Story] 标签用于把任务回溯到具体用户故事
- 每个故事应可独立完成与独立验收
- **实现前先确认测试失败**
- 每完成一个任务或一组逻辑相关任务即提交
- 可在任一 Checkpoint 停下来独立验证
- 避免：含糊任务、同文件冲突、破坏故事独立性的跨故事依赖
