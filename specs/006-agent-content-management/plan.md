# Implementation Plan: 博客 Agent 内容管理

**Branch**: `006-agent-content-management` | **Date**: 2026-08-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-agent-content-management/spec.md`

## Summary

在现有博客内容管理与增强编排器上增加一个私有的“Agent 编排”管理面：由代码内版本化系统清单提供真实、不可任意改序的执行拓扑和锁定安全底座；由 PostgreSQL 保存每个用户的 Agent 文案不可变版本、当前激活关系、隔离预览和正式任务编排快照。前端按“输入与匹配 → 总控诊断 → 条件专业 Agent → Skill/能力 → 质量校验 → 候选保存”分阶段展示，并提供移动端列表替代视图。现有 Blog Skill 仍是内容规范唯一真相；能力注册仍经过安全清单；正式任务提交时冻结 Agent/Prompt/Skill/能力版本，Worker 不读取易变当前配置。

## Technical Context

**Language/Version**: Python 3.12.x；TypeScript 5.7.x；Node.js 24 LTS

**Primary Dependencies**: FastAPI 0.139、Pydantic 2.12、SQLAlchemy 2.0、Alembic 1.18、Celery 5.6；Vue 3.5、Pinia 4、Vue Router 5、Naive UI 2.44；既有 LLM gateway、AsyncJob、Outbox、SSE 与 ActivityLog

**Storage**: PostgreSQL 18.4 保存用户 Agent 不可变版本、激活关系、预览输入/结果索引和任务编排快照；代码内 system manifest 保存稳定拓扑、内置默认文案和锁定安全段；Redis/RabbitMQ 只承担既有锁、短期状态和标识消息

**Testing**: pytest、pytest-asyncio、HTTPX、Testcontainers、JSON Schema/OpenAPI/AsyncAPI drift；Vitest、Vue Test Utils、Playwright；所有权、并发激活、版本固定、密钥检测、日志脱敏和依赖故障测试

**Target Platform**: Linux x86_64/arm64 个人服务器；现代 Chromium、Firefox、Safari；总站 Web/PWA 内部页面

**Project Type**: 前后端分离 Web/PWA + 模块化单体 API + 既有两个 Worker 进程

**Performance Goals**: 95% 拓扑首屏 < 2 秒；95% Agent 版本保存/激活反馈 < 2 秒；95% 异步预览状态变化 < 5 秒；任务编排快照不使现有提交接口 p95 增加超过 100 ms

**Constraints**: 系统拓扑与锁定安全规则不可被用户改序或放宽；保存和激活分离；任务固定版本；消息只传标识；现有 Skill 不复制；能力端点与凭据不进入响应、日志或 Prompt；旧任务不反推当前配置；不新增服务、队列种类或通用 Prompt 平台

**Scale/Scope**: 延续最多 5 个账户；首批 8 个执行节点、5 个主要 Agent 身份、数十个 Blog Skill；每 Agent 历史版本按游标分页；正式 AI 任务量沿用 005 基线

## Constitution Check

*GATE: Passed before Phase 0 research and re-checked after Phase 1 design.*

- [x] Agent 草稿、预览输入和正式编排快照先持久化，再派发任何 AI 或后台工作。
- [x] AI 只能生成预览或文章候选；不能启用 Agent、修改锁定规则、改变拓扑或直接覆盖文章。
- [x] 设计保持 Vue/FastAPI 模块化单体、现有数据库和两个 Worker，无新基础设施。
- [x] 模型与视觉能力继续通过 provider-neutral gateway/安全能力清单，业务服务不直连供应商。
- [x] 预览复用 AsyncJob、Outbox、SSE、幂等、有限重试、DLQ 和 trace ID；正式任务快照与任务同事务。
- [x] Agent、Prompt、Skill、预览和快照按 owner 过滤且默认私有；日志与响应不含正文、完整 Prompt 或密钥。
- [x] REST、预览消息、Agent 配置和任务编排快照均定义版本化契约并做 schema 校验。
- [x] 每个用户故事先安排契约、单元、集成、组件或 E2E 测试，包含 broker/模型/能力失败下的数据存活。
- [x] 页面和任务中心使用业务状态；操作与失败可通过安全 ID、版本、阶段和错误码追踪。

## Phase 0: Research Decisions

完整决策见 [research.md](research.md)。关键结论：

1. 用“代码内系统清单 + 用户数据库覆盖”分离真实拓扑/安全底座与可编辑内容。
2. Agent 身份由稳定 `agent_key` 定义；用户只创建不可变版本，不创建任意生产 Agent。
3. Prompt 分为锁定安全段、可编辑 Agent 指令段和现有 Blog Skill 段，按固定优先级组合。
4. 保存草稿与显式激活分离；激活通过乐观锁与完整校验。
5. 正式任务冻结 eligible Agent 版本和能力清单，运行时补写选择/跳过结果，不读取当前激活配置。
6. 执行图由系统 manifest 自动布局；MVP 不支持拖拽改变运行顺序。
7. Blog Skill 继续复用既有身份/版本/API；能力只显示安全描述和健康状态。
8. 隔离预览先保存输入，再通过现有 AsyncJob/Outbox 执行；消息仅携带 preview/job ID。
9. 内置 manifest 升级通过版本号与基础哈希检测漂移，绝不静默覆盖用户版本。
10. 密钥模式检查、日志字段 denylist 和响应 allowlist 同时保护 Prompt 管理面。

## Phase 1: Architecture and Design

### 1. System manifest and topology

- 新增 `agent_manifest.py`，以稳定 `manifest_version` 定义节点、阶段、边、执行模式、能力依赖、可编辑字段、默认配置和锁定策略引用。
- 首批节点：input/skill-match、orchestrator、editor-agent、logic-agent、data-agent、scene-image-agent、illustration-agent、quality-validator、candidate-save；只有实际 LLM/能力节点称为 Agent。
- 拓扑响应由 manifest 与当前用户激活/版本、现有 Blog Skill、安全能力清单合并得到；边与执行阶段不落入用户可写表。
- manifest 在启动/测试时验证无环、节点/边引用完整、每条生产路径经过质量校验与候选边界。

### 2. Versioned Agent content

- `BlogAgentVersion` 以 `(user_id, agent_key, version_number)` 唯一保存完整 `blog-agent-config.v1`、基础 manifest 版本/默认哈希、内容哈希、结构校验结果和变更说明。
- 版本创建后不可修改；显示名、说明、指令段、受限参数都在完整快照内，避免身份元数据与 Prompt 版本错位。
- `BlogAgentActivation` 每用户/Agent 唯一，记录 `active_version_id`、是否启用、乐观锁版本和更新时间；必经/锁定节点拒绝停用。
- 没有用户激活记录时按 manifest 内置默认运行；“恢复默认”复制当前内置默认为新的用户版本并显式激活。

### 3. Prompt composition and validation

- Prompt 组合顺序固定为：系统锁定安全底座 → 当前冻结总控/Agent 指令 → Blog Skill 结构化规则 → 本次共享诊断/输入 → 用户本次临时要求。
- 可编辑配置只允许 manifest 声明的段和参数；占位符使用明确 allowlist，不支持任意表达式、include、文件路径或环境变量展开。
- 创建版本执行 schema、大小、占位符、密钥模式和参数范围校验；激活时再校验基础 manifest 漂移、依赖和输出契约兼容。
- 依赖不可用分为 warning（运行时可跳过/降级）与 blocking（无法生成有效候选），影响摘要直接返回业务原因。

### 4. Formal-run snapshot

- `BlogOrchestrationSnapshot` 与 `PostAIRun` 一对一，在优化提交事务中固定 manifest/safety 版本、总控版本、每个 eligible Agent 版本、Blog Skill 版本、能力公开清单及哈希。
- Worker 只通过 snapshot ID 加载不可变配置；不在执行中查询 `BlogAgentActivation` 或最新 manifest 默认。
- 确定性 build-plan 完成后，在快照的独立执行结果字段写入 selected/skipped Agent、reason code、能力结果和质量结果；配置快照字段不可改。
- 旧任务无快照时 API 返回 `snapshot_status=legacy_incomplete`，不套用当前配置。

### 5. Isolated preview

- `BlogAgentPreview` 先保存 owner、目标 Agent/版本、样例来源或临时标题/正文、选项、状态和内容哈希，再创建 `blog.agent_preview` AsyncJob 与 Outbox。
- broker 消息只含 job_id/preview_id/trace_id；Worker 从数据库读取输入，复用正式 prompt assembler、plan gates、schema 校验和 provider gateway。
- 预览结果保存结构化执行计划、组合段落名称/哈希/长度、验证结果、用量和安全错误；默认不回传锁定完整系统 Prompt，也不创建 PostRevision/PostAICandidate。
- 用户可删除未被审计策略保留的临时正文；任务元数据、哈希和安全摘要仍可保留。

### 6. Skill and capability integration

- 现有 `/blog/skills`、`BlogSkillVersion`、默认匹配和测试页面不变；拓扑只返回引用与深链。
- `registered_capabilities()` 提供 allowlisted public descriptor；增加健康状态/来源时仍排除 endpoint、token_file、headers 和任何凭据。
- 能力依赖按 manifest 连接到 Agent，展示 `available/disabled/unavailable/unknown` 以及真实 skip/degrade/block 策略。
- Agent 用户启停是编排选择门控，不等于修改部署能力；页面明确两种状态来源。

### 7. API and UI

- 新路由 `/api/v1/blog/agents` 提供 topology、详情、版本创建/列表/比较、激活、恢复默认、预览和运行快照读取。
- 前端新增 `AgentOrchestrationPage.vue`，桌面采用有序阶段列/连线，移动和辅助技术采用同一数据的语义列表；不引入自由画布依赖。
- `AgentEditorPage.vue` 只渲染 manifest 允许字段，锁定规则在旁展示；保存后停留草稿，校验/影响/激活为单独步骤。
- 现有 `SkillListPage` 与详情通过 query 参数支持返回 Agent 定位；任务详情新增编排快照区。

### 8. Ownership, observability and compatibility

- 所有版本、激活、预览、快照查询首先限定 user_id；agent_key 必须存在于请求所绑定的 manifest。
- ActivityLog 只记录对象 ID、agent_key、版本号、操作、基础 manifest、字段名集合和变更摘要，不记录完整 Prompt。
- 日志携带 trace/user/agent/version/job/run/preview ID、长度、哈希、错误码；复用 denylist 并增加 prompt/config/secret 回归测试。
- 迁移为当前用户按需创建激活记录；不回填猜测旧任务配置。当前硬编码总控 Prompt 作为 manifest v1 默认，确保无用户覆盖时行为兼容。

## Contracts

- [contracts/openapi.yaml](contracts/openapi.yaml)：Agent 拓扑、版本、激活、预览和运行快照 REST 契约。
- [contracts/events.asyncapi.yaml](contracts/events.asyncapi.yaml)：`blog.agent_preview.v1` 标识消息。
- [contracts/schemas/blog-agent-config.v1.json](contracts/schemas/blog-agent-config.v1.json)：可编辑 Agent 完整版本配置。
- [contracts/schemas/blog-orchestration-snapshot.v1.json](contracts/schemas/blog-orchestration-snapshot.v1.json)：正式任务冻结配置与执行结果结构。

## Data Model

完整字段、约束、状态与迁移顺序见 [data-model.md](data-model.md)。数据库迁移集中在 `0019_blog_agent_content_management.py`：

1. 创建 Agent 版本与激活表，添加所有者、唯一性、版本和引用约束。
2. 创建编排快照与隔离预览表，并连接既有 `post_ai_runs`/`async_jobs`。
3. 增加按用户/Agent/版本、任务和预览状态的索引。
4. 不改写既有 Blog Skill 版本，不为历史 PostAIRun 猜测快照。

## Verification Strategy

1. 先执行 JSON Schema/OpenAPI/AsyncAPI drift 和 manifest 无环/安全路径测试。
2. 运行 migration upgrade/downgrade，确认现有博客 Skill、任务、候选和文章数据不变。
3. 使用 FakeProvider 验证 Prompt 组合顺序、占位符、锁定段优先级、版本固定和选/跳 Agent 原因。
4. 注入同时保存/激活、manifest 升级、能力缺失、模型超时、broker 停止和 Worker 重投。
5. 执行跨用户 topology/version/preview/snapshot 所有权矩阵及 CSRF 写入测试。
6. 使用密码、JWT、Cookie、PEM、token_file、带凭据 URL 样本验证保存阻止、响应 allowlist 与日志脱敏。
7. 在 360px、桌面、键盘和屏幕阅读器路径验证结构理解、节点定位、编辑/返回和只读替代视图。
8. 运行正式任务回归：无用户 Agent 覆盖时输出与当前内置默认兼容；任务提交后编辑/停用不改变快照。

## Project Structure

### Documentation (this feature)

```text
specs/006-agent-content-management/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── openapi.yaml
│   ├── events.asyncapi.yaml
│   └── schemas/
│       ├── blog-agent-config.v1.json
│       └── blog-orchestration-snapshot.v1.json
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/0019_blog_agent_content_management.py
├── app/
│   ├── models/blog.py
│   ├── main.py
│   ├── modules/posts/
│   │   ├── agent_manifest.py
│   │   ├── agent_schemas.py
│   │   ├── agent_service.py
│   │   ├── agent_router.py
│   │   ├── orchestrator.py
│   │   └── ai_service.py
│   └── workers/tasks/blog.py
└── tests/
    ├── contract/test_blog_agent_contracts.py
    ├── unit/test_blog_agent_manifest.py
    ├── unit/test_blog_prompt_assembly.py
    ├── integration/test_blog_agent_management.py
    ├── integration/test_blog_agent_snapshot.py
    ├── security/test_blog_agent_security.py
    └── reliability/test_blog_agent_preview.py

frontend/
├── src/
│   ├── api/blogAgents.ts
│   ├── router/index.ts
│   └── modules/posts/
│       ├── BlogModuleLayout.vue
│       ├── AgentOrchestrationPage.vue
│       ├── AgentNodeCard.vue
│       ├── AgentEditorPage.vue
│       ├── AgentVersionsPage.vue
│       ├── AgentPreviewPanel.vue
│       ├── SkillListPage.vue
│       └── BlogJobDetailPage.vue
└── tests/
    ├── component/blog-agents.spec.ts
    ├── component/blog-agent-editor.spec.ts
    └── e2e/blog-agent-management.spec.ts
```

**Structure Decision**: 延续现有前后端两个工程与 `posts` 博客领域边界。Agent manifest、版本服务和路由作为现有博客增强编排的子模块；异步预览与正式执行继续使用 `workers/tasks/blog.py`、AsyncJob、Outbox 和既有队列。前端复用博客模块导航、Skill 页面和任务详情，不引入第三个工程或通用工作流编辑器。

## Post-Design Constitution Check

**Result**: PASS。

- 用户 Agent 内容、预览输入和任务快照均在异步调用前持久化。
- 锁定安全段、显式激活、隔离预览、候选机制和不可变版本维护人类控制与可恢复性。
- manifest + 数据库覆盖比把完整拓扑落库更简单，且避免用户绕过安全路径。
- 所有外部模型/能力继续走现有 gateway 与能力注册，不新增供应商耦合。
- 预览与正式任务复用可靠异步设施；消息有界且不含正文/Prompt。
- 所有权、响应 allowlist、密钥阻止与日志摘要覆盖新增私密配置面。
- 四类契约先于实现，任务阶段要求测试先行并覆盖依赖失败与快照不漂移。

## Complexity Tracking

无 Constitution 违例。新增三类持久实体用于分别表达不可变内容版本、当前激活和正式任务快照；合并它们会导致历史不可复现或保存草稿即影响生产，因此不采用单表可变配置。
