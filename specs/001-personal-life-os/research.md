# Research: AI Assist 个人生活操作系统 MVP

**Research date**: 2026-07-22  
**Scope**: 只研究会改变 MVP 架构、可靠性、安全性或可维护性的选择。所有链接均指向官方规范、
官方文档或项目主仓库。

## 1. 模块化单体与后端执行模型

**Decision**: 使用一个 FastAPI 代码库，按 auth/tasks/habits/captures/voice/posts/search/
assistant/notifications/jobs 划分模块。API、Outbox Publisher、Celery Worker 和 Beat 是同一代码镜像的
不同进程，不是微服务。数据库访问统一使用 SQLAlchemy 2 同步 Session + Psycopg 3；普通同步端点由
FastAPI 线程池执行，SSE 本身异步但每次数据库查询使用短 Session。

**Rationale**: 这避免在 API 与 Celery 之间维护 async/sync 两套仓储。Session 不跨线程共享，事务由
应用服务用 `Session.begin()` 明确管理。FastAPI 支持多文件 router 组织，SQLAlchemy 要求每线程/
任务一个 Session。参考 [FastAPI 大型应用](https://fastapi.tiangolo.com/tutorial/bigger-applications/)、
[FastAPI 流式响应](https://fastapi.tiangolo.com/advanced/stream-data/) 和
[SQLAlchemy Session 基础](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)。

**Alternatives considered**: 领域微服务增加部署和分布式一致性成本；全 AsyncSession 会让 Celery 适配
复杂化。两者均不适合个人规模 MVP。

## 2. 版本基线与锁定政策

**Decision**: 实现基线为 Python 3.12.x、FastAPI 0.139.x、Pydantic 2.12.x、SQLAlchemy 2.0.x、
Alembic 1.18.x、Celery 5.6.x、PostgreSQL 18.x、RabbitMQ 4.2.x、Redis 8.x；前端使用 Node 24 LTS、
Vue 3.5.x、TypeScript 7.0.x、Vite 8.1.x、Pinia 4.0.x、Vue Router 5.2.x、Naive UI 2.44.x、
FullCalendar Vue 3 7.0.x、vite-plugin-pwa 1.3.x、Vitest 4.1.x 和 Playwright 1.61.x。

**Rationale**: Python 3.12 对 faster-whisper 和图片原生依赖更保守；Node 24 为 LTS。实现时使用一个
Python lockfile、一个 npm lockfile、`npm ci`，并将容器固定到 patch tag + digest。补丁/次版本经完整
测试合并，主版本单独迁移。参考 [FastAPI 版本建议](https://fastapi.tiangolo.com/deployment/versions/)、
[PostgreSQL 版本策略](https://www.postgresql.org/support/versioning/)、
[Vite 环境要求](https://vite.dev/guide/) 和
[Docker 镜像固定建议](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions)。

**Alternatives considered**: 不使用 `latest` 或无上限依赖。Python 3.13+ 仅在本地 ASR/图片依赖 smoke
test 通过后升级。

## 3. Vue 工程、状态和页面装载

**Decision**: Composition API + `<script setup lang="ts">` + 严格 TypeScript。按领域拆分 Pinia store，
API 调用集中在 typed client/composable；业务路由动态导入，FullCalendar 和 Markdown 编辑器单独 chunk。
Vite 构建之外在 CI 单独运行 `vue-tsc --noEmit`。

**Rationale**: Vite 转译 TypeScript 但不负责类型检查；Pinia 是 Vue 的推荐状态库。参考
[Vue TypeScript](https://vuejs.org/guide/typescript/overview)、
[Pinia](https://pinia.vuejs.org/introduction.html) 和
[Vue 性能建议](https://vuejs.org/guide/best-practices/performance)。

**Alternatives considered**: 不引入 Vuex、巨型全局 store 或第二套 query 状态框架；当真实缓存复杂度出现
时再评估。

## 4. UI、移动布局与日历

**Decision**: 选择 Naive UI；同一响应式应用壳在窄屏使用底部导航，宽屏使用左侧栏。FullCalendar
桌面显示 week time grid，窄屏使用周日期条 + day time grid，并提供 list week 总览。固定事件同时以
`editable:false`、`eventAllow` 和后端校验保护。拖拽保存失败调用 `revert()`，并提供无需拖拽的可访问
替代流程。

**Rationale**: Naive UI 面向 Vue 3/TypeScript，主题定制适合冷静工具型界面；FullCalendar 官方 Vue
适配器支持 interaction 插件和失败回滚。参考 [Naive UI](https://github.com/tusen-ai/naive-ui)、
[FullCalendar Vue](https://fullcalendar.io/docs/vue)、
[eventDrop](https://fullcalendar.io/docs/eventDrop) 和
[Touch 支持](https://fullcalendar.io/docs/touch)。

**Alternatives considered**: Element Plus 同样可用，但空项目没有既有组件需复用；七列周视图直接压缩到
360px 会不可操作，因此移动端保留周上下文但不强行显示七列。

## 5. PWA 缓存和更新

**Decision**: vite-plugin-pwa `generateSW` 只预缓存版本化静态资源和离线说明页；API、SSE、认证、私有
图片一律 NetworkOnly。更新采用提示模式，不自动刷新。MVP 不承诺离线写入或后台上传。

**Rationale**: 自动刷新可能清除未提交的任务或博客输入；缓存私有响应会引入隐私和陈旧状态风险。
参考 [vite-plugin-pwa 更新策略](https://vite-pwa-org.netlify.app/guide/auto-update) 和
[Workbox NetworkOnly](https://developer.chrome.com/docs/workbox/modules/workbox-strategies)。

**Alternatives considered**: 完整离线优先需要本地数据库、冲突合并和上传队列，属于后续独立功能。

## 6. JWT、Cookie、CSRF 与 SSE 鉴权

**Decision**: Access JWT（10–15 分钟）放在 `Secure; HttpOnly; SameSite=Lax; Path=/` 的 `__Host-`
Cookie；refresh 使用随机不透明 token，数据库只存哈希并每次轮换。修改请求需要会话绑定 CSRF header
和 Origin 校验。前端、API 和 SSE 同源；不把 token 放 URL 或 Web Storage。

**Rationale**: 原生 EventSource 不能设置任意 Authorization header，同源 Cookie 可兼容 SSE；HttpOnly
降低 token 被 XSS 直接读取的风险，CSRF 仍需独立防御。参考
[WHATWG EventSource](https://html.spec.whatwg.org/dev/server-sent-events.html)、
[OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)、
[OWASP CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
和 [RFC 9700](https://www.rfc-editor.org/info/rfc9700/)。密码使用 Argon2id，登录按账户和 IP 限流。

**Alternatives considered**: localStorage JWT 被排除；纯服务端 Session 更简单但不符合明确 JWT 约束。

## 7. Durable Job State 与 SSE 重放

**Decision**: `async_jobs` 保存快照，`async_job_events` 保存追加事件。状态更新和事件同一事务提交。
SSE 按 `Last-Event-ID` 查询 PostgreSQL 重放；Redis Pub/Sub 只唤醒查询，Redis 不可用时周期轮询数据库。
无游标或游标超出保留期时发送 `jobs.snapshot`。每标签页只建一个全局 EventSource。

**Rationale**: Redis Pub/Sub 会丢失断线期间事件，不能承担重放；PostgreSQL 事件游标和快照可恢复。
EventSource 标准定义了 `Last-Event-ID` 和自动重连；FastAPI 提供 SSE 响应。参考
[FastAPI SSE](https://fastapi.tiangolo.com/tutorial/server-sent-events/) 和
[WHATWG SSE](https://html.spec.whatwg.org/dev/server-sent-events.html)。

**Alternatives considered**: WebSocket 对单向状态更新不必要；仅 snapshot 会丢失短暂完成/失败通知上下文。

## 8. 事务、迁移与 Transactional Outbox

**Decision**: 一个应用服务操作一个短事务；业务数据、activity、async job 和 outbox 同事务写入，事务
内不调用网络 Provider。独立 `outbox-publisher` 进程用 `FOR UPDATE SKIP LOCKED` + 租约 claim，提交后
发布持久消息并等待 publisher confirm，再标记 published。过期租约可回收。

**Rationale**: Outbox 消除数据库提交和 broker publish 的双写缺口；publish 成功后进程崩溃仍可能重复，
因此消费者必须幂等。参考 [Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox)、
[PostgreSQL SELECT locking](https://www.postgresql.org/docs/current/sql-select.html) 和
[RabbitMQ Reliability](https://www.rabbitmq.com/docs/reliability)。Alembic autogenerate 必须人工审阅，CI 运行
`alembic check`，参考 [Alembic autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)。

**Alternatives considered**: HTTP 事务内直接 `task.delay()` 会产生不可原子双写；用 Celery Beat 唤醒
Publisher 会让恢复路径反过来依赖 broker，均拒绝。

## 9. RabbitMQ、Celery 和幂等

**Decision**: 使用 durable quorum queues、持久 JSON 消息、confirm publish、manual ack、delivery limit
和每队列 DLQ。命令显式路由；worker-fast 处理 critical/notification/schedule/search，worker-heavy 处理
voice/image/llm/maintenance。Heavy 初始并发 1、prefetch 1；Fast 并发按服务器 2–4。仅幂等任务启用
late ack/worker-lost reject。Celery result 默认关闭，业务状态只看 PostgreSQL。

**Rationale**: Celery 对 quorum queues 要求 confirm，文档也强调 late ack 可能重复执行、retry 应使用
backoff/jitter 且任务不得同步等待子任务。参考
[Celery RabbitMQ](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/rabbitmq.html)、
[Celery Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html)、
[Celery Routing](https://docs.celeryq.dev/en/stable/userguide/routing.html)、
[RabbitMQ Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues) 和
[Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)。

**Alternatives considered**: Redis broker 不满足本项目明确路由/DLQ诉求。Redis lock 只降低并发；正确性
由 PostgreSQL unique、conditional update、consumer receipt 和 idempotency record 保证。

## 10. 提醒调度

**Decision**: Beat 每分钟发出短扫描命令；worker 以 `SKIP LOCKED` claim 到期 reminder，在同一事务创建
唯一 notification delivery 和 outbox command。重要提醒进 critical，普通提醒进 notification。时间以 UTC
瞬时值 + IANA 时区保存。

**Rationale**: 长 ETA/countdown 任务会占 Worker 能力且重启恢复复杂；持久 due rows 可重扫。参考
[Celery RabbitMQ/ETA 限制](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/rabbitmq.html)。

**Alternatives considered**: 不把未来数天提醒长期驻留在 broker/worker 内存。

## 11. PostgreSQL 全文搜索

**Decision**: PostgreSQL 18 使用加权 tsvector、GIN、`websearch_to_tsquery`、`ts_rank_cd` 和限定结果后的
`ts_headline`。启用 trusted `pg_trgm` 为中文和物品型号提供子串/模糊回退。搜索先查已提交业务数据；
异步 search_documents 只做跨实体派生加速，不能成为唯一可搜索来源。

**Rationale**: PostgreSQL 推荐 GIN 作为全文索引，并内置排名/高亮；pg_trgm 可索引相似匹配。参考
[FTS Indexes](https://www.postgresql.org/docs/current/textsearch-indexes.html)、
[Text Search Functions](https://www.postgresql.org/docs/current/functions-textsearch.html) 和
[pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html)。

**Alternatives considered**: Elasticsearch/OpenSearch 增加一个近似业务真相和显著运维成本；向量数据库
属于第二阶段。

## 12. Storage Gateway 与 2026 MinIO 风险

**Decision**: Provider-neutral Storage Gateway。生产默认使用 Web Root 外的本地私有卷；后端所有权检查
后返回 Nginx `X-Accel-Redirect` 到 `internal` location。S3 adapter 使用私有 bucket 和短期预签名 URL
（普通预览约 60 秒、下载不超过 5 分钟），签名查询参数从日志脱敏。Compose 保留可选 `s3` profile，
但不把旧 MinIO 社区二进制作为公网生产默认。

**Rationale**: Nginx internal location 可高效发送已鉴权本地文件；预签名 URL 是 bearer token。MinIO
官方社区服务端仓库于 2026-04-25 归档并说明旧二进制不再维护，固定旧 digest 不能消除维护终止风险。
参考 [Nginx internal](https://nginx.org/en/docs/http/ngx_http_core_module.html#internal)、
[S3 presigned URL](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html) 和
[MinIO 官方仓库](https://github.com/minio/minio)。

**Alternatives considered**: 商业 AIStor 或其他受维护 S3 服务可经 adapter 替换；数据库 BLOB 和 public
bucket 不满足备份体积/私有鉴权要求。

## 13. 上传、图片与 EXIF

**Decision**: API 流式写临时 object key，逐块计数，不只信 Content-Length。初始限制：图片 25 MiB/
50 MP、语音 50 MiB、Markdown 2 MiB。扩展名、声明 MIME、magic bytes 和真实解码必须一致；图片只允许
JPEG/PNG/WebP。先保存 raw original，Worker 读取 orientation 并自动旋转，然后生成清除 EXIF/XMP/IPTC/
GPS 的展示副本、缩略图和 WebP，重新打开验证元数据已移除。

**Rationale**: `UploadFile` 适合大文件落盘/流式读取；Content-Type 可伪造，必须多层验证；剥离 EXIF
前必须先使用 orientation。参考 [FastAPI UploadFile](https://fastapi.tiangolo.com/tutorial/request-files/)、
[OWASP File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) 和
[ImageMagick auto-orient/strip](https://imagemagick.org/script/command-line-options.php/)。

**Alternatives considered**: 上传时同步完整图片处理会延迟 durable acceptance；原图不进入公开博客。

## 14. Compose、Nginx 和健康模型

**Decision**: 仅支持 Docker Compose V2。增加一次性 migrate 服务；PostgreSQL、RabbitMQ、Redis 和可选
S3 服务有真实 healthcheck。backend 等数据库/迁移/本地存储就绪；RabbitMQ、Redis、AI、邮件故障只
标记 degraded，不阻止基础保存。只暴露 Nginx 80/443，内部管理端口不发布。SSE 关闭 proxy buffering，
上传路由设置大小限制。Secrets 按服务最小挂载。

**Rationale**: Compose 只等容器运行，不自动等 ready；长格式 depends_on 可等待 healthy/成功的一次性
任务。参考 [Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/)、
[Compose secrets](https://docs.docker.com/reference/compose-file/secrets/)、
[Nginx proxy buffering](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering) 和
[Nginx body limit](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size)。

**Alternatives considered**: 固定 sleep/wait-for-it 不能表达运行期状态；Caddy 自动 HTTPS 更简洁，但
Nginx 与本地 `X-Accel-Redirect` 更直接且符合原始部署约束。

## 15. 邮件、备份和恢复

**Decision**: MailGateway 使用部署者 SMTP relay，不自建公网 MTA。优先 465 implicit TLS；587 必须
STARTTLS 成功。发送以 `(reminder_id,channel,scheduled_at)` 去重，4xx 退避、明确 5xx 失败；SMTP 无法
保证 crash 边界绝对 exactly-once，接受极少重复并记录 unknown。默认备份目标 RPO 24h/RTO 2h：每日
`pg_dump -Fc` + 资产同步 + manifest/checksum，异地加密保存；至少季度做真实恢复演练。

**Rationale**: `pg_dump` custom format 支持选择和并行 restore；SMTP Submission 应要求 TLS。参考
[PostgreSQL pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html)、
[RFC 8314](https://www.rfc-editor.org/info/rfc8314/) 和
[Gmail sender guidelines](https://support.google.com/mail/answer/81126?hl=en)。

**Alternatives considered**: 复制在线 PostgreSQL volume 不能保证一致；PITR 可作为更高可靠部署选项，
自建 Postfix 的信誉/DNS/退信运维不适合轻量个人系统。

## 16. 结构化 AI、追踪与安全日志

**Decision**: Pydantic v2 是 REST/SSE/message/LLM Schema 的实现源，消息与 AI 模型 `extra='forbid'`
并启用严格校验；所有 schema 显式版本。HTTP 接收/生成 W3C trace context，trace/correlation/causation
写入 outbox、消息、job、LLM log 和结构化日志。默认不记录 JWT、签名 URL、图片/音频、完整 prompt、
文章正文或转写正文。

**Rationale**: Pydantic 可生成 Draft 2020-12/OpenAPI 3.1 Schema，严格模式避免静默类型转换；W3C Trace
Context 提供跨进程标准。参考 [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/)、
[Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/) 和
[W3C Trace Context](https://www.w3.org/TR/trace-context/)。

**Alternatives considered**: 手写 JSON Schema 与 DTO 容易漂移；外部 telemetry exporter 为可选，不是基础
保存的运行依赖。

## 17. 测试策略

**Decision**: 后端 pytest 覆盖领域状态机、时区/DST、所有权、幂等、Provider 端口；真实 PostgreSQL
验证迁移/约束/并发 outbox；真实 RabbitMQ/Redis 验证 confirm、redelivery、DLQ、Worker 死亡和 SSE 重放。
前端 Vitest + Vue Test Utils 做 store/组件，Playwright 覆盖真实拖拽、移动导航、cookie、SSE 和 PWA。
故障矩阵必须覆盖 commit 前、commit 后 publish 前、confirm 后标记前、上传后 DB 失败和 AI 中断。

**Rationale**: Celery eager mode 不代表真实 worker；Vue 官方推荐 Vitest/Vue Test Utils/Playwright。
参考 [Celery testing](https://docs.celeryq.dev/en/stable/userguide/testing.html)、
[FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/)、
[Vue testing](https://vuejs.org/guide/scaling-up/testing.html) 和
[Playwright projects](https://playwright.dev/docs/test-projects)。

**Alternatives considered**: 只 mock broker/DB 无法验证本项目最关键的可靠性保证；完整浏览器矩阵只在关键
流水线运行，以控制个人项目成本。
