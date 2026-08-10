# 修复复盘：B站音视频导入与 Radio 历史转写迁移（2026-07-30）

## 目标与结果

AI Assist 博客的“从链接导入”现已识别 Bilibili 视频页和 `b23.tv` 短链，复用 Radio 已有的下载、Whisper 转写和历史记录能力。普通网页仍走原有抓取链路。

Radio 原有 34 条历史转写已全部创建为博客文章。现网端到端测试又产生 1 条 Radio 记录并自动创建博客，因此最终核对为：Radio 35 条、AI Assist 35 个唯一外部记录、35 篇非空文章、失败 0、缺失 0。

## 原链路分析

- 前端入口：`UrlCreateDialog.vue` 调用 `POST /api/v1/posts/captures/url`。
- AI Assist：capture 事务创建 `Post + PostSource + AsyncJob + Outbox`，Outbox 再投递 Celery；正文使用 Markdown。
- Radio：`POST /api/tasks/speech2text/bilibili` 创建异步任务，`GET /api/tasks/{id}` 查询状态和结果。
- Radio 成功结果包含视频信息、完整转写和 transcript ID。
- Radio 历史接口原先只有 `limit`，且服务端最大 200，没有全量分页元数据。

## 实施内容

### Radio

- 历史记录接口新增向后兼容的 `offset` 分页。
- 响应新增 `total`、`limit`、`offset`、`has_more`、`next_offset`。
- 保留原 `items` 和单页最大 200 的行为。

### AI Assist 后端

- 增加统一 URL 类型识别，支持 `bilibili.com/video/BV...` 与 `b23.tv/...`，并严格校验 scheme、host 和路径。
- 增加带连接/读取超时的 Radio 客户端；服务地址与凭据均走配置和 Docker secret。
- B 站导入使用现有 Outbox、AsyncJob 和 Celery heavy worker，不在 HTTP 请求中等待转写。
- Celery 每次只做一次提交或查询，通过持久化 Radio task ID 继续轮询，不占用 worker 等待。
- 成功后按既有 Markdown 格式写入视频标题和完整转写正文，并创建修订记录。
- Radio 连接、DNS、超时、5xx 和异常响应统一映射为 `RADIO_SERVICE_UNAVAILABLE`，前端显示“B站音视频处理服务当前不可用，请稍后重试。”。
- 无效/受限视频、任务失败和空转写分别返回可识别错误，不创建空文章。
- `PostSource` 增加 `external_system`、`external_record_id`、`external_task_id`，并建立用户维度的外部记录唯一索引。

### 前端

- B 站链接按钮和处理中状态改为“保存并转写”语义。
- Radio 不可用、链接不可解析、转写失败和空正文使用既有提示组件显示明确中文信息。
- 普通网页导入交互与请求保持不变。

### 历史迁移

新增独立脚本 `scripts/migrate_radio_records_to_blog.py`，支持：

- `--dry-run`
- `--base-url`
- `--limit`
- `--force`
- `--start-id`
- `--max-records`
- `--user-id` / `--user-email`
- `--report-file`

脚本按 `external_system + external_record_id` 幂等，默认已存在则跳过；`--force` 才更新。空正文或无 ID 记录会明确跳过，单条失败不会中断其余记录，最终会检查统计等式是否平衡。

## 现网迁移结果

第一次 dry-run：

~~~json
{
  "radio_total": 34,
  "eligible": 34,
  "would_create": 34,
  "missing_body": 0,
  "failed": 0,
  "balanced": true
}
~~~

正式迁移：

~~~json
{
  "radio_total": 34,
  "eligible": 34,
  "created": 34,
  "existing": 0,
  "skipped": 0,
  "failed": 0,
  "balanced": true
}
~~~

端到端测试完成后的最终幂等核对：

~~~json
{
  "radio_total": 35,
  "eligible": 35,
  "created": 0,
  "existing": 35,
  "missing_body": 0,
  "failed": 0,
  "balanced": true
}
~~~

JSON 明细保存在：

- `/www/wwwlogs/aiassist/radio-migration-2026-07-30.json`
- `/www/wwwlogs/aiassist/radio-migration-idempotency-2026-07-30.json`
- `/www/wwwlogs/aiassist/radio-migration-final-check-2026-07-30.json`

## 现网端到端验证

使用有效 `b23.tv` 短链经公开博客导入接口提交：

~~~text
HTTP:               202
job type:           blog.bilibili_import
final job status:   completed
final progress:     100
source status:      completed
title:              已替换为 B 站视频标题
body chars:         130
external record id: 已保存
~~~

测试同时发现全局 Celery annotation 会把任务重试上限覆盖为 5。已改为在 B 站轮询的 `self.retry` 调用中显式传入专属上限，并补充回归测试；已完成的 Radio 任务随后被恢复并正常落库，没有重复转写。

## 自动化验证

~~~text
AI Assist 后端定向测试：68 passed
前端组件测试：28 passed
Radio 分页测试：1 passed
前端生产构建：passed
Ruff：passed
compileall：passed
git diff --check：passed
数据库 model drift：passed
~~~

覆盖普通网页分流、Bilibili/B23 识别、非法 URL、Radio 成功/连接失败/超时/500/异常响应/空正文、长轮询、全量分页、dry-run、幂等、force、统计平衡和前端错误提示。

## 执行命令

dry-run：

~~~bash
docker compose run --rm backend \
  python scripts/migrate_radio_records_to_blog.py --dry-run --limit 100
~~~

正式迁移：

~~~bash
docker compose run --rm backend \
  python scripts/migrate_radio_records_to_blog.py \
  --limit 100 \
  --report-file /logs/aiassist/radio-migration-report.json
~~~

若存在多个启用用户，需要额外指定 `--user-id` 或 `--user-email`。凭据通过 secret 注入，不应作为命令参数或日志内容传入。

## 日志检索

Kibana data view：`logs-aiassist-*`

~~~text
event: "blog_bilibili_radio_task_submitted"
event: "blog_bilibili_import_completed"
event: "blog_bilibili_import_failed"
error_code: "RADIO_SERVICE_UNAVAILABLE"
job_id: "<任务 ID>"
source_id: "<来源 ID>"
trace_id: "<接口或任务详情中的 trace ID>"
~~~

日志只记录稳定错误码、安全诊断分类和业务 ID，不记录 Radio 密码、Cookie、Token 或内部鉴权信息。

## 回滚

- 应用回滚：切回上一版应用镜像即可；数据库变更是可空的增量列，可先保留，避免破坏已迁移文章的外部身份信息。
- 数据回滚：以 `post_sources.external_system = 'radio'` 和迁移 JSON 中的 post ID 精确核对后删除对应文章；执行前必须备份数据库。不要按标题批量删除。
- Schema 回滚：确认不再运行新代码、并已导出外部身份映射后，才执行 `alembic downgrade 0012_fix_revision_source`。
- Radio 分页回滚：旧客户端不依赖新增字段，恢复旧接口实现不会影响原 `limit/items` 调用方。

## 遗留风险

- Radio 的认证会话保存在进程内；Radio 重启后 AI Assist 会自动重新认证一次。
- B 站访问策略、登录限制和媒体可用性属于外部条件，失败时会保留可重试任务与明确错误码。
- 单次转写最长等待当前为 6 小时，可通过环境变量调整；超过上限会终止轮询并提示超时。
