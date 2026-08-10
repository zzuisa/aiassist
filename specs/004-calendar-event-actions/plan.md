# Implementation Plan: 日历事件快捷操作与视觉优化

**Branch**: `004-calendar-event-actions` | **Date**: 2026-07-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-calendar-event-actions/spec.md`

## Summary

在现有任务/日历模块上增加事件单击或轻点操作面板，复用 `Task.status` 与 `Task.importance`
完成可撤销的完成/重要切换，并将重要事件绑定到以 `start_at` 为锚点、提前 240 分钟的唯一邮件提醒。
新增一对一事件备注和一对多私有图片附件模型，复用上传会话、对象存储网关、Outbox、图片 Worker
和受保护资产访问模式。前端通过 FullCalendar 的事件点击、事件内容和时间槽样式钩子实现 popover、
名称优先布局、完成 emoji、柔和红色重要背景和已流逝时间灰化。

## Technical Context

**Language/Version**: Python 3.12.x；TypeScript 5.7.x；Node.js 24 LTS

**Primary Dependencies**: FastAPI 0.139、Pydantic 2.12、SQLAlchemy 2.0、Alembic 1.18、
Celery 5.6、Vue 3.5、Pinia 4、Naive UI 2.44、FullCalendar 6.1、Vite 8

**Storage**: PostgreSQL 18.4 保存任务、备注、附件元数据、提醒与 Outbox；本地私有对象目录或
S3 兼容存储保存图片二进制；Redis 仅用于临时协调；RabbitMQ 承载图片处理与提醒命令

**Testing**: pytest、pytest-asyncio、HTTPX、Testcontainers；Vitest、Vue Test Utils、Playwright；
OpenAPI/AsyncAPI schema drift 检查

**Target Platform**: Linux x86_64/arm64 个人服务器；现代 Chromium、Firefox、Safari；移动 PWA

**Project Type**: 前后端分离 Web/PWA + 模块化单体 API + 既有异步 Worker

**Performance Goals**: 正常网络下事件状态更新 p95 < 2 秒；备注文字保存 p95 < 2 秒；单张图片
上传完成后 3 秒内出现可追踪附件记录；重要提醒在计划时点后 60 秒内开始发送；日历滚动和点击不引入
可感知卡顿

**Constraints**: 完成和重要状态可撤销；重要提醒严格锚定事件开始时间；图片先进入私有对象存储再建立
业务关联；不把二进制写入数据库或消息；所有读写执行所有权检查；状态写入、审计与 Outbox 同事务；
视觉含义不能只依赖颜色；不改变固定事件和 AI 调整边界

**Scale/Scope**: 延续项目最多 5 个账户、100,000 条任务和 50,000 个媒体资产的 MVP 基线；
本增量覆盖周日历已有事件、单个事件的一份备注和多批图片，不新增日历视图或外部日历同步

## Constitution Check

*GATE: Passed before Phase 0 and re-checked after Phase 1 design.*

- [x] 用户状态和备注在返回成功前持久化；图片在对象保存且附件关联提交后才视为接受。
- [x] 本功能不引入 AI 写入；完成和重要状态由用户显式切换并可撤销，固定事件规则不变。
- [x] 设计保留现有 Vue/FastAPI 模块化单体和 Docker Compose，不新增业务服务或基础设施。
- [x] 邮件和对象存储继续通过既有 provider-neutral gateway，业务模块不直接依赖供应商。
- [x] 图片处理和邮件提醒复用持久化状态、Outbox、幂等键、有限重试、DLQ 与 trace ID。
- [x] 备注和附件默认私有；任务、上传会话、附件和访问 URL 均校验同一用户所有权。
- [x] 变更先定义 REST 与消息契约；既有 SSE 和 AI schema 不受影响。
- [x] 每个用户故事先安排契约、单元、集成或组件测试，再实现对应代码和迁移。
- [x] 图片派生与邮件投递保留可见持久状态和可操作错误，不向用户暴露 Worker/队列术语。

**Post-design result**: PASS。没有 Constitution 例外或需记录的复杂度豁免。

## Architecture Decisions

### Event state and calendar query

- “已完成”继续使用 `Task.status=completed`，取消完成恢复为 `todo` 并清空 `completed_at`；所有变更保留
  `version` 乐观锁、活动日志和 `task.updated` Outbox 事件。
- “重要”复用 `Task.importance`：操作面板开启时写 `4`，关闭时写 `0`；任何大于 0 的既有值均按重要
  样式展示，避免新增重复布尔字段。
- 周日历事件查询包含时间范围内的 `todo`、`in_progress` 和 `completed` 记录，仅未排期区继续排除
  completed；因此完成事件不会从日历消失。

### Important email reminder lifecycle

- `Reminder` 增加用途和时间锚点语义；专用用途 `important_start_4h`、锚点 `start_at`、偏移 240 分钟、
  channel `email`、`is_critical=true`。
- 同一用户/任务只能存在一条该用途提醒。标重要时创建或重新激活，取消重要时取消尚未发送项，
  `start_at` 修改时在同一事务中重算，已发送提醒不因反复切换而重复发送。
- 距开始不足 4 小时时将 `trigger_at` 设为当前时间；已经开始或无开始时间时不调度并通过派生的
  reminder summary 返回 `not_applicable` 或 `missing_start`。SMTP 未配置或投递失败沿用 delivery 状态，
  重要状态本身不回滚。

### Durable event notes and image associations

- 每个任务最多一份 `TaskNote`，文字使用独立 `content` 和 `version`，不占用 `Task.description`，避免与
  原有任务描述语义混合。
- `TaskNoteAsset` 是每张图片的稳定业务记录，持有所属用户、任务备注、完成上传会话、私有原图键、
  派生预览键、顺序和处理状态。图片二进制只存在对象存储。
- 上传会话新增 `task_note_image` purpose，沿用现有图片大小/MIME 限制。首批附件可与备注创建/编辑
  同事务关联；后续批次逐张关联，使某张失败不会回滚其他成功图片。
- 每个附件关联成功后写 Outbox 并异步生成移除定位元数据的预览图。原图始终私有；日历备注默认只
  请求预览访问 URL，原图下载需要显式授权请求。
- 既有 maintenance Worker 增加仅针对过期且未关联的 `task_note_image` 上传清理；清理按稳定状态和
  过期时间扫描，并在删除对象后更新上传记录，避免关联失败留下永久孤立对象。

### REST and UI integration

- 现有 `PATCH /tasks/{task_id}` 负责完成/取消完成和重要/取消重要，响应增加重要提醒摘要；避免增加
  只包装现有 Task 字段的动作端点。
- 新增事件备注读取/保存、追加图片和受保护图片访问端点，详细 schema 见
  [contracts/openapi.yaml](contracts/openapi.yaml)。图片处理命令见
  [contracts/events.asyncapi.yaml](contracts/events.asyncapi.yaml)。
- `CalendarPage.vue` 使用 FullCalendar `eventClick` 打开独立 `CalendarEventPopover.vue`；事件自定义内容
  先渲染标题，再渲染时间。完成 emoji 带可访问文本，重要背景使用新增语义 token。
- `slotLaneClassNames` 根据用户本地当前时间为已流逝时间格添加类；每分钟刷新边界。灰色仅作用于网格
  层，不覆盖事件卡片，深浅主题均验证文字对比度。
- `CalendarEventNoteEditor.vue` 使用支持 `multiple` 的文件选择并按批次调用上传流程；成功项即时保留，
  失败项单独展示和重试。状态或备注保存成功后触发现有 tasks store 变更信号并刷新日历版本。

## Project Structure

### Documentation (this feature)

```text
specs/004-calendar-event-actions/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── openapi.yaml
│   └── events.asyncapi.yaml
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/0009_calendar_event_actions.py
├── app/
│   ├── main.py
│   ├── models/
│   │   ├── tasks.py
│   │   ├── scheduling.py
│   │   └── voice.py
│   ├── modules/
│   │   ├── tasks/
│   │   │   ├── router.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── calendar_router.py
│   │   │   ├── calendar_service.py
│   │   │   ├── note_router.py
│   │   │   └── note_service.py
│   │   ├── notifications/reminder_service.py
│   │   └── uploads/{router.py,service.py}
│   └── workers/tasks/{images.py,notifications.py,maintenance.py}
└── tests/
    ├── contract/test_calendar_event_actions_api.py
    ├── integration/
    │   ├── test_calendar_event_actions.py
    │   ├── test_task_note_assets.py
    │   └── test_important_reminders.py
    ├── reliability/test_calendar_event_action_failures.py
    ├── security/test_task_note_asset_security.py
    └── unit/test_important_reminder_rules.py

frontend/
├── src/
│   ├── api/{calendar.ts,taskNotes.ts,tasks.ts}
│   ├── modules/calendar/
│   │   ├── CalendarPage.vue
│   │   ├── CalendarEventPopover.vue
│   │   ├── CalendarEventNoteEditor.vue
│   │   └── useTaskNoteUploads.ts
│   └── styles/tokens.css
└── tests/
    ├── component/calendar-event-actions.spec.ts
    ├── component/calendar-event-note.spec.ts
    └── e2e/calendar-event-actions.spec.ts
```

**Structure Decision**: 保持现有前后端两个工程。状态和提醒规则留在 tasks/notifications 既有模块；
事件备注作为 tasks 子模块；上传、对象访问和图片派生复用现有跨模块服务，不创建新的业务服务。

## Complexity Tracking

无 Constitution 违例。新增两张业务表、一项提醒用途和一项上传 purpose 是实现可靠文件关联与
开始时间提醒所需的最小数据变化；未引入通用媒体重构、新队列、新供应商或新的前端状态框架。
