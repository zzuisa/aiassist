# Implementation Plan: 个人信息总站博客内容管理扩展

**Branch**: `005-blog-content-management` | **Date**: 2026-07-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-blog-content-management/spec.md`

## Summary

在既有 `posts` 模块上扩展来源采集、内部内容状态、动态结构化字段、可版本化 Skill、固定输入的异步 AI 运行、完整候选快照、字段级三方审核、待整理、模块搜索、时间轴和组织治理，并优先补齐移动端博客列表与结构化主分类。Markdown 继续作为正文规范格式，Milkdown 提供受限富文本视图；URL 先保存来源与草稿，再由受 SSRF 约束的 HTTPX + Trafilatura 后台提取。所有长任务复用总站 `AsyncJob`、SSE、Outbox、通知和 LLM gateway，文章当前版本只有人工保存或显式/策略允许的候选应用事务能够推进；每次部署同时生成安全的版本元数据，向用户展示更新内容和历史状态，并在构建前完成 Git commit/push。

现有 `Post.status=draft/private/published` 继续承担公开兼容语义；新增 `content_status` 承担本次内部整理生命周期。本功能不新增公开页面、权限系统、模型平台、搜索服务或 Worker 类型。

## Technical Context

**Language/Version**: Python 3.12.x；TypeScript 5.7.x；Node.js 24 LTS

**Primary Dependencies**: FastAPI 0.139、Pydantic 2.12、SQLAlchemy 2.0、Alembic 1.18、Celery 5.6、HTTPX 0.28、Trafilatura 2.1；Vue 3.5、Pinia 4、Vue Router 5、Naive UI 2.44、Milkdown（Vue/Crepe 当前兼容版）、markdown-it-py、nh3；既有 LLM 与对象存储 gateway

**Storage**: PostgreSQL 18.4 保存文章、来源、完整版本快照、组织关系、Skill 版本、AI 运行绑定、候选审核、设置和词云快照；私有对象存储保存可选原始网页快照和文章资产；Redis 只用于锁/唤醒/短期缓存；RabbitMQ 只携带标识和紧凑参数

**Testing**: pytest、pytest-asyncio、HTTPX、Testcontainers、JSON Schema/OpenAPI/AsyncAPI drift 检查；Vitest、Vue Test Utils、Playwright；格式往返语料、SSRF、所有权、并发版本、消息重投和依赖故障测试

**Target Platform**: Linux x86_64/arm64 个人服务器；现代 Chromium、Firefox、Safari；总站 Web/PWA 内部页面

**Project Type**: 前后端分离 Web/PWA + 模块化单体 API + 既有异步 Worker

**Performance Goals**: 95% 文字/剪切板保存反馈 < 2 秒；95% 在线任务状态变化 < 5 秒；100,000 篇验收数据下 95% 博客组合搜索首屏 < 2 秒；常规自动保存 p95 < 2 秒；文章列表和时间轴首屏无感知阻塞；移动端分类选择与行操作反馈 p95 < 2 秒

**Constraints**: 原始内容与草稿先于抓取/AI/索引持久化；Markdown 为唯一正文真相；AI 只写候选且按字段策略应用；文章改变时强制待合并；数字、日期、代码、命令、URL 和引用确定性保护；任务固定文章与 Skill 版本；URL 获取防 SSRF；所有查询按所有者过滤；公开兼容不在本次扩展；不新增 Worker 服务或基础设施

**Scale/Scope**: 延续最多 5 个账户、100,000 篇文章、50,000 个媒体资产的个人服务器基线；覆盖 11 个用户故事、15 个 MVP 页面与 8 个 MVP 弹窗/抽屉，P1/P2/P3 功能按故事独立交付

## Constitution Check

*GATE: Passed before Phase 0 and re-checked after Phase 1 design.*

- [x] 来源与文章在任何抓取、AI、索引或通知前持久化；对象写入完成并建立业务关联后才确认媒体保存。
- [x] AI 输出只形成候选；正文和高风险字段需要确认，允许的自动填充仍可通过版本恢复；任务期间修改强制待合并。
- [x] 设计保持现有 Vue/FastAPI 模块化单体、两个 Worker 进程和 Docker Compose，不增加独立博客、搜索、抓取或 Skill 服务。
- [x] LLM 和对象存储继续经过 provider-neutral gateway；URL 提取是模块内有界能力并有稳定错误分类。
- [x] AsyncJob 是用户可见状态真相；业务写入与 Outbox 同事务，消费者具备幂等、有限重试、DLQ、锁和 trace ID。
- [x] 文章、来源、快照、版本、Skill 和任务默认私有并执行所有权检查；URL 抓取不发送用户凭据，日志不记录原始私密内容。
- [x] REST、SSE 派生状态、消息和 `blog-optimization.v1` 输出都定义版本化契约并进行 schema 校验。
- [x] 每个用户故事先安排契约、单元、集成、组件或 E2E 测试；采集、AI、队列和搜索失败场景验证内容存活。
- [x] 页面使用业务状态而非队列术语；任务详情、活动记录和结构化日志提供安全诊断信息。
- [x] 移动端博客列表采用单列内容优先布局；左右滑动动作均提供按钮替代、取消回弹和高风险确认。
- [x] 移动端总站底部导航固定在视口底部，使用明确层级、不透明背景、底部安全区和内容预留空间，避免内容遮挡主导航。
- [x] 结构化主分类优先于标签/关键词进入列表首屏、筛选、编辑器属性和批量操作；分类树有界且停用历史可追踪。
- [x] 部署更新记录只保存安全版本元数据；commit/push 位于新镜像构建之前，失败时阻止部署继续。

**Pre-research gate**: PASS。无宪法违例和未解决澄清项。

## Phase 0: Research Decisions

完整研究见 [research.md](research.md)。主要结论：

1. 增量扩展 `posts`，用独立 `content_status` 保留现有发布兼容。
2. Markdown 作为正文规范格式；Milkdown 提供 Vue 富文本编辑和 Markdown 更新监听。
3. URL 先保存再后台获取，使用 HTTPX 受限获取与 Trafilatura Markdown/元数据提取。
4. URL 获取逐跳执行 SSRF 校验，不带用户 Cookie/认证信息。
5. 核心筛选字段关系化，动态字段用版本化 JSONB，修订保存全部可恢复字段。
6. AI 修订与候选审核记录分离；部分字段应用产生新的确认修订。
7. 通用任务状态复用 `AsyncJob`，博客运行表冻结输入、Skill、模型和策略。
8. Skill 使用可变身份、不可变版本和唯一作用域默认绑定。
9. AI 使用 `blog-optimization.v1` 严格输出与确定性保护 token 校验。
10. 搜索延续正式数据直查 + `SearchDocument` GIN 派生索引，不增加新搜索服务。
11. 分类/标签复用总站身份并通过博客扩展表治理；关键词保持独立。
12. 移动端使用保守手势阈值和可发现的按钮菜单，滑动只作为快捷入口，不成为唯一操作路径。
13. 文章首期只有一个主分类；分类选择在列表、编辑器和批量操作中复用同一所有权/启用校验。
12. 词云是低优先级、可重建的持久快照，不进入文章保存路径。

## Phase 1: Architecture and Design

### 1. Existing compatibility boundary

- 保留 `/api/v1/posts` 的既有基本创建、读取、保存、AI 修订、发布/取消发布和公开 RSS 行为。
- 扩展响应字段但不改变现有字段含义；新客户端使用细分的捕获、内容、候选、Skill、组织和设置资源。
- `Post.status` 不映射规格中的“已完成”；新增 `content_status` 并由内部页面使用。
- 现有正文级 AI 修订迁移为完整快照的兼容子集；旧记录补齐最小快照，不回写 AI 生成字段。
- 本次 UI 不新增或强化公开发布入口；保留既有行为用于回归兼容。

### 2. Durable content and revision lifecycle

- 空白、剪切板和快速记录在一个事务中创建 Post、PostSource、首个 `PostRevision`、Activity 和必要 Outbox。
- URL 创建在首个事务中保存 Post（`content_status=pending_parse`）、PostSource（`status=pending`）、首个版本和提取 Job/Outbox；响应不等待网络。
- `PostRevision.snapshot_json` 是完整不可变快照，包含正文、标题/摘要、组织 ID、时间、语言和结构化字段。`Post.markdown` 等当前列是高效当前投影。
- 用户保存使用 `Post.version` 乐观锁；成功保存创建 `source=user_edit` 修订并原子更新当前投影与 `current_revision_id`。
- 恢复历史版本从目标快照创建 `source=restore` 新修订；历史链不删除。
- 删除沿用软删除和现有公开限制，来源、候选和运行按保留关系继续可审计。

### 3. Capture normalization and URL extraction

- 剪切板识别在浏览器完成权限和预览；提交包含原始表示、规范化候选、媒体引用和检测类型。服务器再次清洗 HTML、规范化 Markdown 并校验长度。
- HTML 清洗使用现有 nh3 风格允许列表；可见文本、链接、表格、引用和代码先提取再比较，防止清洗静默删文。
- URL Worker 只接收 `source_id/job_id`；读取持久 URL 后逐跳验证目标、流式限制响应、可选保存原始快照，再以 Trafilatura 输出 Markdown 与元数据。
- 提取成功在事务中写来源、更新草稿和创建修订；若文章已被人工编辑，只更新来源并创建可选提取候选，不覆盖正文。
- 失败或部分成功写业务化错误与可用字段；用户可仅保留来源、粘贴正文或重试。

### 4. Editor and rendering

- `BlogEditorShell.vue` 管理标题、属性、保存和路由；`MarkdownSourceEditor.vue` 管理源文本；`RichMarkdownEditor.vue` 封装 Milkdown；`MarkdownPreview.vue` 负责安全预览。
- 两种模式只交换 Markdown 字符串，不保存编辑器内部文档树。切换先执行往返检查；发现不受支持节点时创建版本并要求确认降级。
- 预览沿用 `markdown-it-py`/前端等价解析规则和安全渲染策略，默认禁用原始 HTML。普通读者视觉增强优先使用受限 `visual-plan` JSON，由前端以紧凑卡片式 SVG 渲染并支持 PNG 导出；技术图继续在隔离容器中只读执行 Mermaid。公式和代码高亮不影响存储文本。
- 自动保存采用 1.5 秒停顿 + 显式保存/离开保护，始终携带版本；失败保留编辑缓存并显示未保存状态。
- 文件和图片复用 UploadSession 的 `attachment`/`post_cover` purpose 与保护访问，不新增媒体中心。

### 5. Content organization

- `Post.content_class` 使用稳定 key；`PostContentType` 是用户可配置类型，包含所属大类、显示顺序、启用状态和字段 schema。
- 核心动态数据在 `structured_data_json`，服务按内容类型 schema 校验；切换类型不删除未知键，只改变显示/校验集合。
- `Category(kind=post)` 与 `PostTag` 继续复用；Profile/Alias 表提供层级、说明、颜色、启用和别名。
- `PostKeyword` 与 `PostKeywordLink` 单独建模，支持来源、权重、停用、规范词和同义词。
- 合并分类/标签/关键词在事务中重定向关系、记录 `TaxonomyMerge` 和 Activity；大量重算通过低优先级任务执行。

### 6. Skill lifecycle and matching

- Skill 配置只属于当前用户；当前版本必须完整校验后才能启用或设默认。
- 保存已存在 Skill 时分配递增 `version_number`、写不可变配置和 Activity，再更新 `current_version_id`。
- 默认绑定表对每个用户的 global/category/content-type scope 唯一；替换默认显式返回被替换绑定。
- 提交 AI 前依次尝试手动 Skill、内容类型默认、大类默认、全局默认；每一项都验证启用、适用和版本完整性。
- `PostAIRun` 保存选中 `skill_version_id` 以及字段策略快照；之后的 Skill 修改不影响任务。

### 7. AI execution, validation and candidate review

- API 在文章当前版本成功保存后创建 `AsyncJob(job_type=blog.optimize)`、`PostAIRun` 和 Outbox；幂等键由 user/post/base_revision/optimization_type/skill_version/request nonce 构成。
- Worker 阶段依次更新 `current_step`: `preprocessing`、`analyzing`、`skill_execution`、`model_call`、`validating`、`saving_candidate`。
- 预处理生成模型输入和保护 token 清单；输入大于 Skill 限制时按固定规则分段或失败，不静默截断。
- LLM gateway 使用 `BlogOptimizationV1`；schema 修复最多一次。分类/标签建议只解析为候选，不能创建或合并组织项。
- 校验输出格式、必填字段、类型、允许的字段路径、组织项所有权/合法性、保护 token、来源字段和新增事实风险。
- AI Assist 的完整优化先经过 provider-neutral 的 Blog Enhancement Orchestrator：总控只生成一次共享诊断，按价值、选项、能力注册和 Agent 预算选择 Editor/Logic/Data/Scene/Illustration；低价值视觉增强返回 `skipped`，不伪造 Skill 调用。Qwen/DeepSeek 等模型接收统一的 `BlogEnhancementResultV1`，Worker 在候选边界适配回兼容的 `blog-optimization.v1`，并将安全的编排报告写入候选校验摘要。
- 全部或部分有效结果写 `PostRevision(source=ai_candidate)` 与 `PostAICandidate`。若当前修订等于基线，根据冻结策略自动应用允许字段或置 `waiting_user`；不等则 `merge_required`。
- 字段应用事务锁定 Post 和 Candidate，重新检查版本，从当前快照叠加选中字段，创建 `source=ai_applied` 修订，记录 `PostCandidateDecision` 和 Activity，并发变化返回冲突而不修改候选。

### 8. Job, notification and observability integration

- REST 任务接口对博客增加过滤条件和派生 `display_status`；SSE 使用既有 durable event log，不新增长连接。
- URL 提取、AI 优化、关键词重算和词云使用不同 `job_type`，但均经同一任务中心和通知。
- Worker 在关键阶段和终态写 JobEvent；完成/失败通知只发送摘要与页面链接，不包含文章正文。
- 日志携带 trace/job/post/source/skill_version ID，只记录内容长度、哈希和校验代码，不记录原文、Prompt、Cookie 或响应正文。
- 幂等消费以 Outbox event ID 和 PostAIRun/Source 状态为屏障；重试不创建重复候选或重复应用。

### 9. Search, timeline and word cloud

- 博客模块查询可组合 Post 核心列、Category/Tag/Keyword 关系、来源 URL 和 JSONB 结构字段；所有路径先限定 user_id 和 deleted_at。
- `SearchDocument` 写入标题、摘要、Markdown、标签、分类、关键词和扁平结构字段；全局搜索沿用 `post` 类型。
- 文章列表首期直接返回 `category_id`，前端以分类缓存映射名称；分类选择失败不改变文章当前主分类。
- `app/AppShell.vue` 负责总站响应式导航；移动端底部导航使用固定定位和独立层级，`.content` 预留导航高度并适配 `safe-area-inset-bottom`。
- 直接数据查询保证刚保存文章可找到；派生 GIN/trigram 索引负责规模下的排序、高亮和代码/CJK 兜底。
- 时间轴按 `occurred_at` 或 `created_at` 范围游标分页；无发生时间时 API 返回 `time_basis=created_at`。
- 词云生成读取正式文章和规范 Tag/Keyword，应用停用词/阈值，保存 `PostWordCloudSnapshot`；失败不删除上次成功结果。

### 10. Settings and safe defaults

- `BlogSettings` 一用户一行，JSON 分组为 create、clipboard、url_capture、ai_apply、word_cloud，并包含 schema_version。
- 服务对 Skill、内容类型、分类和标签默认值做所有权、启用和适用校验；失效默认按明确顺序回退并返回 warning。
- 自动应用默认关闭；设置和 Skill 策略取更严格值。正文、来源、代码/命令/引用和已有人工作值不能通过设置放宽为无确认覆盖。
- 设置更新只影响新创建或新提交任务，不回写历史来源、修订、Skill 版本或 PostAIRun。
- 移动端手势状态只属于当前页面交互，不持久化为业务状态；归类/归档/丢弃仍通过显式业务接口写入并记录 Activity。

### 11. Deployment update transparency and Git gate

- `frontend/public/release-history.json` 是由部署入口生成并随代码提交的安全版本清单，只包含版本、提交、时间、环境、状态、摘要和变更文件。
- `AppShell.vue` 启动后读取最新清单，以浏览器本地已查看版本作为去重标记；新版本显示更新公告，公告可一次导航到 `/settings/updates`。
- `ReleaseHistoryPage.vue` 展示当前版本和历史版本的运行状态、部署状态、Git push 状态、commit 短 ID、发布时间和可展开的变更文件。
- `deploy.sh up` 在构建 frontend/backend 镜像前执行工作区检查、commit 和当前分支 push；push 失败立即退出，不进入构建和部署阶段。发布元数据不读取或写入任何 secret。

## Contracts

- [contracts/openapi.yaml](contracts/openapi.yaml)：博客私有 REST、扩展 Job 视图和受保护来源快照访问。
- [contracts/events.asyncapi.yaml](contracts/events.asyncapi.yaml)：URL 提取、AI 优化、搜索刷新、词云/关键词重算命令。
- [contracts/schemas/blog-optimization.v1.json](contracts/schemas/blog-optimization.v1.json)：严格 AI 输出。
- [contracts/schemas/blog-enhancement.v1.json](contracts/schemas/blog-enhancement.v1.json)：Blog Enhancement Orchestrator 的总控诊断、决策、增强和质量结果。
- [contracts/schemas/blog-skill-config.v1.json](contracts/schemas/blog-skill-config.v1.json)：不可变 Skill 版本配置。

## Data Model

完整实体、关系、校验、迁移与状态见 [data-model.md](data-model.md)。数据库变更集中在 `0011_blog_content_management.py`，迁移顺序：

1. 扩展 `posts`、`post_revisions` 及上传 purpose，保持旧列非破坏性。
2. 创建来源、内容类型、组织扩展、关键词、Skill、AI 运行/候选/决策、博客设置和词云快照表。
3. 回填现有 Post 的 `content_status`、完整 revision snapshot 和内容类型默认值。
4. 增加所有权、唯一性、状态、索引和外键约束；大表索引采用可回滚策略。
5. 保留 `status`、`published_at`、slug 与公开接口数据，不执行发布状态转换。

## API and Message Versioning

- 新接口位于现有 `/api/v1/posts`、`/api/v1/blog-*` 命名空间下；既有路径向后兼容。
- OpenAPI 请求默认 `extra=forbid`，写接口使用 CSRF 与所有权校验，版本冲突返回稳定 `version_conflict`/`base_conflict`。
- 异步消息均为 v1 envelope，仅传 `job_id/source_id/run_id/post_id` 和 trace/idempotency 信息。
- AI schema 以 `schema_version=blog-optimization.v1` 固定；任务记录同时保存 schema 版本。
- 前后端类型从契约生成或由 drift 测试验证，禁止仅靠手写接口漂移。

## Failure and Recovery Matrix

| Failure | Durable state kept | User-visible outcome | Recovery |
|---|---|---|---|
| Clipboard permission denied | No server record; local input unchanged | Explain browser permission and paste fallback | Paste manually/retry permission |
| Clipboard normalization partial | Raw source + usable text | Partial warning per image/block | Edit or retry missing asset |
| URL invalid/SSRF blocked | Source + note when basic URL accepted; otherwise input retained | Safe target rejected | Correct URL or keep as text |
| URL timeout/login/forbidden | Post + source + initial revision | `待整理`, reason and saved fields | Retry or paste body |
| Broker unavailable after create | Post/source/job + pending Outbox | Saved; task awaiting dispatch | Outbox reconcile |
| Model unavailable/timeout | All article versions + failed Job/Run | Current article unchanged | Bounded retry or new model |
| Invalid AI schema | Raw provider response not persisted as article | Failed/partial validation summary | One repair then retry |
| Protected token changed | Candidate blocked or field requires confirmation | Risk shown, no auto apply | Reject/select safe fields |
| Article edited during AI | Current revision + candidate | `待合并` | Three-way field selection |
| Candidate apply races with save | Both current and candidate remain | Version conflict | Reload comparison |
| Search/word-cloud worker failure | Current article + last successful derived data | Article usable; stale timestamp | Rebuild derived result |
| Skill modified/disabled | Historical SkillVersion | Running task unchanged | New task chooses valid version |

## Project Structure

### Documentation (this feature)

```text
specs/005-blog-content-management/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── openapi.yaml
│   ├── events.asyncapi.yaml
│   └── schemas/
│       ├── blog-optimization.v1.json
│       └── blog-skill-config.v1.json
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/0011_blog_content_management.py
├── app/
│   ├── main.py
│   ├── models/
│   │   ├── posts.py
│   │   └── blog.py
│   ├── modules/posts/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   ├── capture_router.py
│   │   ├── capture_service.py
│   │   ├── url_extractor.py
│   │   ├── skill_router.py
│   │   ├── skill_service.py
│   │   ├── taxonomy_router.py
│   │   ├── taxonomy_service.py
│   │   ├── ai_router.py
│   │   ├── ai_service.py
│   │   ├── query_router.py
│   │   └── query_service.py
│   ├── modules/search/service.py
│   ├── modules/jobs/{router.py,schemas.py,service.py,sse.py}
│   ├── services/llm/schemas.py
│   ├── services/storage/
│   └── workers/tasks/{blog.py,search.py}
└── tests/
    ├── contract/
    │   ├── test_blog_content_api.py
    │   ├── test_blog_async_contracts.py
    │   └── test_blog_ai_schema.py
    ├── integration/
    │   ├── test_blog_capture.py
    │   ├── test_blog_editor_versions.py
    │   ├── test_blog_ai_pipeline.py
    │   ├── test_blog_candidate_merge.py
    │   ├── test_blog_skills.py
    │   ├── test_blog_management.py
    │   ├── test_blog_search_timeline.py
    │   └── test_blog_taxonomy.py
    ├── reliability/test_blog_failure_matrix.py
    ├── security/test_blog_url_and_ownership.py
    ├── performance/test_blog_search_100k.py
    └── unit/
        ├── test_blog_normalization.py
        ├── test_blog_skill_matching.py
        ├── test_blog_field_policy.py
        └── test_blog_protected_tokens.py

frontend/
├── package.json
├── src/
│   ├── api/{posts.ts,blogCapture.ts,blogSkills.ts,blogTaxonomy.ts,blogQueries.ts}
│   ├── api/releases.ts
│   ├── router/index.ts
│   ├── app/AppShell.vue
│   ├── modules/releases/{ReleaseUpdateDialog.vue,ReleaseHistoryPage.vue}
│   └── modules/posts/
│       ├── BlogModuleLayout.vue
│       ├── PostListPage.vue
│       ├── PostCreateDialog.vue
│       ├── ClipboardCreateDialog.vue
│       ├── UrlCreateDialog.vue
│       ├── QuickCaptureDialog.vue
│       ├── PostEditorPage.vue
│       ├── PostViewPage.vue
│       ├── RichMarkdownEditor.vue
│       ├── MarkdownSourceEditor.vue
│       ├── MarkdownPreview.vue
│       ├── PostPropertySidebar.vue
│       ├── TriagePage.vue
│       ├── BlogJobsPage.vue
│       ├── BlogJobDetailPage.vue
│       ├── CandidateComparePage.vue
│       ├── PostVersionsPage.vue
│       ├── TimelinePage.vue
│       ├── TaxonomyPage.vue
│       ├── WordCloudPage.vue
│       ├── SkillListPage.vue
│       ├── SkillEditorPage.vue
│       ├── SkillVersionsPage.vue
│       ├── SkillTestPage.vue
│       └── BlogSettingsPage.vue
└── tests/
    ├── component/
    │   ├── blog-capture.spec.ts
    │   ├── blog-editor.spec.ts
    │   ├── blog-ai-candidate.spec.ts
    │   ├── blog-skills.spec.ts
    │   ├── blog-management.spec.ts
    │   └── blog-discovery.spec.ts
    └── e2e/blog-content-management.spec.ts
```

**Structure Decision**: 延续前后端两个工程。现有 `posts` 是博客领域入口；新增 `models/blog.py` 保存支持实体，避免把一个模型文件无限扩大。捕获、Skill、组织、AI 和查询按 `posts` 子模块拆分路由/服务，但仍共享同一数据库事务和部署。异步工作继续使用 `workers/tasks/blog.py` 与既有队列拓扑；搜索与任务中心只做兼容扩展。

## Verification Strategy

1. 先运行 schema drift、迁移 upgrade/downgrade 和旧 Posts API 回归，确认发布兼容。
2. 每个用户故事先运行其 contract/unit/integration/component 测试，再运行 E2E 独立验收。
3. 对 URL 使用伪 DNS、重定向链、IPv4/IPv6 私网、超大/压缩响应和超时注入。
4. 对 AI 使用 FakeProvider 驱动完整、部分、畸形、修改保护 token 和新增事实输出。
5. 对任务使用 broker 停止、重复 Outbox、Worker 崩溃、重试和取消，验证不重复候选/应用。
6. 对并发使用 V1 提交任务、V2 人工保存、候选返回和再次竞争应用的三方路径。
7. 对所有列表、详情、资源、Skill、任务和搜索执行跨用户所有权矩阵。
8. 以 100,000 篇文章运行模块搜索 p95、时间轴游标分页和词云后台生成性能验收。
9. 在 360px、桌面、键盘和屏幕阅读器路径验证新建、编辑、候选审核、任务状态、更新公告和底部导航不遮挡内容。
10. 在干净、脏工作区、无上游分支和 push 失败场景验证部署 Git gate 与安全 release metadata。

## Post-Design Constitution Check

**Result**: PASS。

- 数据模型将原始来源、当前投影、不可变版本和 AI 候选分离，持久化边界清楚。
- 契约将 AI、消息、REST 和状态派生版本化；没有自由格式 AI 直接写业务数据。
- URL 抓取增加必要的 SSRF 安全边界，但没有引入通用抓取服务。
- 两个现有 Worker、Outbox、AsyncJob、SSE、通知、搜索和存储能力被复用；无新基础设施。
- 所有高风险写入都有版本检查、活动记录和恢复路径；日志不包含私密正文。
- 发布更新有可读公告、历史版本状态和安全元数据；Git commit/push gate 在镜像构建前执行。
- 测试计划覆盖契约先行、所有权、幂等、依赖失败、迁移和数据存活。

## Complexity Tracking

无 Constitution 违例。新增支持表数量较多，源于需要同时满足不可变全文版本、字段级候选审核、Skill 固定版本及分类/标签/关键词明确分离；已拒绝独立博客服务、工作流引擎、搜索服务、通用爬虫、知识图谱和实时词云等更复杂方案。
