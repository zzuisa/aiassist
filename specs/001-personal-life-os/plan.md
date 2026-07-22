# Implementation Plan: AI Assist 个人生活操作系统 MVP

**Branch**: `001-personal-life-os` | **Date**: 2026-07-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-personal-life-os/spec.md`

## Summary

以模块化单体实现可自部署的个人生活操作系统。Vue PWA 提供移动优先的今日、任务日历、习惯、
收藏、博客、搜索和 AI 操作界面；FastAPI 单体按业务模块组织；PostgreSQL 保存最终业务状态；
本地私有对象目录默认保存原始和派生资产，并保留 S3 兼容适配器；RabbitMQ/Celery 处理可靠异步任务；
Redis 仅承担临时缓存、锁和事件唤醒。
所有采集流程先可靠保存，再通过 Transactional Outbox 触发后台处理。日程与内容的 AI 变更采用
“生成预览/差异 → 用户确认 → 独立应用”的两阶段流程。

完整的 15 项设计输出在 [design.md](design.md)，数据定义在 [data-model.md](data-model.md)，接口与
消息契约位于 `contracts/`。

## Technical Context

**Language/Version**: Python 3.12.x（后端）；TypeScript 7.x + Node.js 24 LTS（构建）

**Primary Dependencies**: FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、Celery、Psycopg 3、
Vue 3、Vite、Pinia、Vue Router、Naive UI、FullCalendar、vite-plugin-pwa

**Storage**: PostgreSQL 18.4 业务数据、全文检索和 SSE 事件；本地私有目录（默认）或 S3 兼容对象存储；
Redis 8.8.0 临时缓存、锁和 SSE 唤醒；RabbitMQ 4.3.2 可靠异步消息。中间件版本基线以
[deployment.md 第 7 节](deployment.md#7-固定版本清单) 为准

**Testing**: pytest、pytest-asyncio、HTTPX、Testcontainers；Vitest、Vue Test Utils、Playwright；
Schemathesis 或等价 OpenAPI 契约验证

**Target Platform**: Linux x86_64/arm64 个人服务器；现代 Chromium、Firefox、Safari；移动 PWA

**Project Type**: 前后端分离的 Web/PWA + 模块化单体 API + 两类异步 Worker

**Performance Goals**: 文字保存 p95 < 2 秒；上传完成到基础记录可见 p95 < 3 秒；关键词搜索
p95 < 2 秒；在线任务状态传播 p95 < 5 秒

**Constraints**: 用户数据先保存；固定事件不可被 AI 移动；结构化输出校验；所有权隔离；
单机 Docker Compose；消息不含二进制/无界文本；Celery 状态不作业务真相

**Scale/Scope**: 最多 5 个个人账户、100,000 条业务记录、50,000 个媒体资产；MVP 9 个用户故事、
约 20 个核心实体、单一区域部署

## Constitution Check

*GATE: Passed before Phase 0 and re-checked after Phase 1 design.*

- [x] 用户内容在 AI 或长任务前持久化：上传/语音/文字接口先提交业务记录和 outbox。
- [x] AI 变更可预览/确认/撤销且固定事件不移动：独立 preview 与 apply 契约。
- [x] 保持模块化单体和 Compose：没有业务微服务或额外编排平台。
- [x] AI、语音、邮件和存储经统一 Gateway：业务模块只依赖端口协议。
- [x] 异步状态持久化：Outbox、幂等键、重试、DLQ、锁和 trace 均有数据与消息设计。
- [x] 所有权、私有默认和安全资产访问：契约要求当前用户过滤与短期签名 URL。
- [x] REST、SSE、消息和 AI 输出均有版本化契约：见 `contracts/`。
- [x] 测试先行并覆盖依赖失败：`tasks.md` 在每个实现切片前安排测试任务。
- [x] 用户可见任务中心与运维可观测性：`async_jobs` 是最终状态并传播业务文案。

**Post-design result**: PASS。无 Constitution 例外需要豁免。

## Architecture Decisions

### Request and persistence path

1. 边缘代理终止 TLS，同源转发静态前端、REST、SSE 和受保护资产请求。
2. API 验证身份和所有权，在单个 PostgreSQL 事务内写业务记录、活动记录和 outbox 事件。
3. API 返回稳定实体 ID；前端立即渲染 `pending/queued` 状态，不等待 AI。
4. 独立 Outbox Publisher 进程以租约和跳过锁定行批处理 pending 事件，带发布确认写入 RabbitMQ。
5. Worker 用事件 ID/场景幂等键去重，更新 `async_jobs`，将短期进度发布到 Redis 用户频道。
6. Job 状态变更与追加事件同事务写入 PostgreSQL；Redis 只唤醒 SSE 查询新事件。断线按事件 ID 重放，
   游标过期时发送快照校准。

### Transaction and consistency boundaries

- 业务写入、活动记录和 outbox 插入同事务；对象上传采用“先写临时对象，再提交业务记录，再异步
  finalize/cleanup”的补偿型流程，避免数据库与对象存储假装具有分布式事务。
- Outbox 发布为至少一次；消费者以 `event_id` 和业务幂等键实现恰好一次的业务效果。
- 日程预览保存基线 `task.version`；应用时逐项检查版本，冲突项不覆盖并返回重新生成建议。
- 用户值和 AI 值分列或以明确 provenance 存储；AI 不能更新 `source=user` 的字段。

### API and realtime boundaries

- REST 使用 `/api/v1`，统一错误为 RFC 9457 Problem Details，并在响应头返回 trace ID。
- 登录采用同源、Secure、HttpOnly Cookie 中的短期 JWT，刷新凭据轮换并保存在服务端；所有非安全
  方法要求 CSRF token。该选择允许浏览器原生 EventSource 使用同源凭据而不在 URL 泄露令牌。
- SSE 单用户端点 `/api/v1/events/jobs`，事件为 `jobs.snapshot`、`job.updated` 和 `notification.created`。
- 资产下载通过所有权检查后返回短期签名 URL；公开博客封面使用独立公开派生对象或代理响应。

## Project Structure

### Documentation (this feature)

```text
specs/001-personal-life-os/
├── spec.md
├── plan.md
├── design.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── openapi.yaml
│   ├── events.asyncapi.yaml
│   ├── sse.md
│   └── llm-schemas.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── alembic/
├── app/
│   ├── api/v1/
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── modules/
│   │   ├── auth/
│   │   ├── tasks/
│   │   ├── habits/
│   │   ├── captures/
│   │   ├── voice/
│   │   ├── posts/
│   │   ├── search/
│   │   ├── assistant/
│   │   ├── notifications/
│   │   └── jobs/
│   ├── services/
│   │   ├── llm/
│   │   ├── speech/
│   │   ├── storage/
│   │   ├── mail/
│   │   └── outbox/
│   ├── workers/
│   └── main.py
├── tests/
│   ├── contract/
│   ├── integration/
│   └── unit/
└── pyproject.toml

frontend/
├── src/
│   ├── api/
│   ├── app/
│   ├── components/
│   ├── composables/
│   ├── layouts/
│   ├── modules/
│   │   ├── today/
│   │   ├── calendar/
│   │   ├── tasks/
│   │   ├── habits/
│   │   ├── captures/
│   │   ├── posts/
│   │   ├── search/
│   │   ├── assistant/
│   │   └── settings/
│   ├── router/
│   ├── stores/
│   └── styles/
├── tests/
│   ├── component/
│   └── e2e/
└── package.json

deploy/
├── nginx/
├── postgres/
├── rabbitmq/
└── scripts/

compose.yaml
.env.example
Makefile
```

**Structure Decision**: 采用两个源码工程（frontend/backend）和一个部署目录；后端业务边界位于同一
Python 包和进程中，Worker 复用相同模型与服务代码。共享契约以 `specs/.../contracts` 为设计源，
实现阶段生成/维护前端类型并用契约测试防漂移。

## Phase 0: Research

研究结果记录在 [research.md](research.md)，覆盖前端状态与 PWA、浏览器 SSE 鉴权、同步数据库访问、
独立 Outbox Publisher、RabbitMQ 拓扑、对象补偿事务、PostgreSQL 全文搜索、受保护本地/S3 资产和
Compose 健康编排。
任何具体依赖版本以实现时锁文件与镜像摘要为准，不使用无上限的 `latest` 标签。

## Phase 1: Design and Contracts

- [design.md](design.md)：按需求指定的 15 个章节给出页面、架构、队列、Worker、部署和风险设计。
- [data-model.md](data-model.md)：实体字段、索引、关系、所有权和状态机。
- [contracts/openapi.yaml](contracts/openapi.yaml)：MVP REST 接口、鉴权和错误模型。
- [contracts/events.asyncapi.yaml](contracts/events.asyncapi.yaml)：命令/事件 envelope、队列与路由键。
- [contracts/sse.md](contracts/sse.md)：事件流、快照重连和前端处理规则。
- [contracts/llm-schemas.md](contracts/llm-schemas.md)：场景配置、语音任务、收藏分类和日程建议结构。
- [quickstart.md](quickstart.md)：部署、迁移、首次账户、健康检查、备份与验收路径。

## Complexity Tracking

无 Constitution 违例。RabbitMQ 和 Redis 分别承担可靠异步与短期唤醒/锁；文件使用 Storage Gateway，
默认本地私有目录并提供可选 S3 profile。未增加 Kafka、Kubernetes、WebSocket、GraphQL、向量数据库
或业务微服务。Outbox Publisher 是同一后端镜像的运行进程，不是业务微服务。
