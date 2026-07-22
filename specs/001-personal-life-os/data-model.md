# Data Model: AI Assist 个人生活操作系统 MVP

## 1. 通用约定

- 主键使用 UUID，由应用生成；外部响应不得暴露自增序列。
- 所有用户数据表包含 `user_id`，仓储层默认注入用户过滤；跨实体外键之外仍验证两端同一用户。
- 瞬时时间使用 `timestamptz` 并存 UTC；本地日期使用 `date`；用户时区使用 IANA 名称。
- 可编辑核心实体包含 `version int not null default 1`，PATCH 使用乐观并发控制。
- `created_at`、`updated_at` 为必填；需要恢复/审计的内容用 `deleted_at` 软删除。
- 枚举在应用和数据库约束中同步定义；JSONB 仅用于可演进载荷、快照和少量动态元数据，
  不替代需要查询、约束或关联的列。
- 用户正文与 AI 输出分开保存。AI 值带 `source=ai`、场景、模型日志引用、置信度和生成时间。
- 金额为 `numeric(14,2)` + `char(3)` ISO 币种；时长统一使用正整数分钟或秒并在字段名注明。

## 2. 核心实体

### users

| 字段 | 类型 | 约束/说明 |
|---|---|---|
| id | uuid | PK |
| email | citext | unique, not null |
| password_hash | text | not null；只存强哈希 |
| display_name | varchar(80) | not null |
| timezone | varchar(64) | not null, default `Europe/Berlin` |
| locale | varchar(16) | not null, default `zh-CN` |
| status | varchar(16) | active/disabled |
| notification_preferences | jsonb | 受 `NotificationPreferences` Schema 校验（`extra='forbid'`）：
`in_app_enabled`、`email_enabled`、`critical_email_enabled`、`quiet_hours_start`、`quiet_hours_end`。
未配置 SMTP 时 `email_enabled` 只能为 false |
| created_at/updated_at/last_login_at | timestamptz | last_login 可空 |

### refresh_sessions

`id, user_id, token_hash, family_id, expires_at, rotated_at, revoked_at, user_agent_hash,
ip_prefix, created_at`。只保存 refresh token 哈希；同一 token 再次使用时撤销 token family。

### tasks

| 字段 | 类型 | 约束/说明 |
|---|---|---|
| id/user_id | uuid | PK / FK users |
| type | varchar(24) | task/fixed_event/habit_task/reminder/note |
| title | varchar(240) | not null |
| description | text | 用户正文 |
| status | varchar(24) | todo/in_progress/completed/cancelled |
| priority | smallint | 0..4 |
| importance | smallint | 0..4 |
| start_at/due_at | timestamptz | 可空；due >= start when both |
| estimated_minutes/actual_minutes | integer | >=0 |
| category_id | uuid | FK categories, 可空 |
| is_fixed/is_ai_adjustable/is_splittable | boolean | fixed 时 ai_adjustable 必为 false |
| energy_level | varchar(16) | low/medium/high, 可空 |
| recurrence_rule | text | 受控 RRULE 子集，可空；仅模板任务可填 |
| recurrence_parent_id | uuid | self FK，同用户；由重复模板生成的实例指向模板，可空 |
| occurrence_date | date | 实例所属本地日期，可空；与 recurrence_parent_id 同时存在 |
| source_type/source_id | varchar(32)/uuid | voice/capture/habit/post/manual 等 |
| habit_id/habit_date | uuid/date | 习惯任务来源，可空 |
| completed_at | timestamptz | completed 时必填 |
| version | integer | 乐观锁 |
| created_at/updated_at/deleted_at | timestamptz | 软删除 |

约束/索引：

- unique `(user_id, habit_id, habit_date)` where habit_id is not null，保证每日习惯任务幂等。
- unique `(user_id, recurrence_parent_id, occurrence_date)` where recurrence_parent_id is not null，
  保证普通重复任务每个本地日期只生成一个实例。
- index `(user_id,status,due_at)`、`(user_id,start_at)`、`(user_id,deleted_at)`。
- exclusion constraint 可作为后续严格固定事件重叠检查；MVP 允许冲突但显式提示，因此不硬拒绝重叠。

### reminders

`id, user_id, task_id, channel(in_app/email), trigger_at, offset_minutes, status(scheduled,
claimed,sent,failed,cancelled), is_critical, idempotency_key, last_error, retry_count,
sent_at, created_at, updated_at`。

唯一约束 `(user_id,idempotency_key)`；索引 `(status,trigger_at)`。任务时间变化时重算尚未发送提醒，
已发送记录保留。

### schedule_previews

`id, user_id, scope_start, scope_end, status(processing,ready,partially_applied,applied,
expired,failed), baseline_hash, suggestions_json, explanation, async_job_id, expires_at,
created_at, applied_at`。

每条 suggestion 包含 `suggestion_id, task_id, task_version, old_start, old_end, new_start,
new_end, conflicts[], reason, recommendation, selectable`。固定任务 suggestion 的 selectable 必为 false。

### habits

`id, user_id, name, description, recurrence_rule, suggested_time_local, target_minutes,
minimum_amount, unit, priority, auto_create_task, is_ai_adjustable, active_from, active_until,
status(active,paused,archived), version, created_at, updated_at, deleted_at`。

### habit_logs

`id, user_id, habit_id, local_date, status(completed,partial,skipped), amount, duration_seconds,
skip_reason(no_time,too_tired,forgot,unrealistic_plan,not_suitable,other), skip_note,
task_id, started_at, completed_at, created_at, updated_at`。

唯一约束 `(user_id,habit_id,local_date)`；部分完成是否计入 streak 由业务规则配置，默认仅 completed。

### captures

| 字段 | 类型 | 约束/说明 |
|---|---|---|
| id/user_id | uuid | PK / owner |
| type | varchar(24) | item/inspiration/note/image/document/link/location/purchase/blog_material |
| title_user/title_ai | varchar(240) | AI 不覆盖用户标题 |
| description_user/description_ai | text | 来源分离 |
| category_id/category_ai_id | uuid | 用户确认分类 / AI 建议分类 |
| brand_user/brand_ai | varchar(120) | 来源分离 |
| model_user/model_ai | varchar(120) | 来源分离 |
| material_user/material_ai | varchar(120) | 来源分离 |
| color_user/color_ai | varchar(80) | 来源分离 |
| storage_location_user/storage_location_ai | varchar(240) | 来源分离 |
| purchased_at/purchase_place/purchase_price/currency | mixed | 购买信息，可空 |
| usage_status | varchar(24) | owned/wishlist/in_use/stored/disposed/unknown |
| ocr_text | text | AI/处理派生，不作用户事实 |
| ai_confidence | numeric(4,3) | 0..1，可空 |
| processing_status | varchar(24) | pending/processing/ready/needs_input/failed |
| possible_duplicate_of | uuid | self FK，同用户 |
| version/timestamps/deleted_at | mixed | 乐观锁、软删除 |

### capture_assets

`id, user_id, capture_id, upload_id, role(original,thumbnail,preview,attachment,audio),
storage_key, bucket, media_type, byte_size, width, height, sha256, exif_json_sanitized,
gps_removed, processing_version, status(uploading,ready,failed,deleted), created_at, deleted_at`。

`storage_key` 为内部值，永不直接返回客户端。索引 `(user_id,sha256)` 用于重复提示；原始对象不可
被派生处理原地覆盖。

### upload_sessions

`id, user_id, purpose, object_key_temp, expected_media_type, max_bytes, status(created,
uploaded,completed,expired,aborted), sha256_client, expires_at, created_at, completed_at`。

complete 操作按 `(user_id,id)` 幂等；过期临时对象由 maintenance 小批清理。

### voice_records

`id, user_id, asset_id, status(uploaded,transcribing,parsing,waiting_user,confirmed,
discarded,failed), provider_key, transcript, transcript_language, parsed_payload_json,
schema_version, confirmed_entity_type, confirmed_entity_id, error_code, error_message,
async_job_id, created_at, updated_at, confirmed_at`。

只有 `waiting_user` 可 confirm；confirm 事务创建正式实体、来源关系和 outbox，并将状态改为 confirmed。

### posts

`id, user_id, slug, title, status(draft,private,published), current_revision_id, category_id,
cover_asset_id, seo_title, seo_description, excerpt, published_at, version, created_at,
updated_at, deleted_at`。

`slug` 对 published 内容全局唯一；未发布文章的私有读取仍按 user。公开查询只能返回 published。

### post_revisions

`id, user_id, post_id, parent_revision_id, source(user,ai), markdown, change_summary,
llm_log_id, applied_at, created_at`。AI revision 创建时不更新 `posts.current_revision_id`；apply 才更新。

### categories / tags / join tables

- `categories(id,user_id,name,kind,created_at,updated_at)`，unique `(user_id,kind,lower(name))`。
- `tags(id,user_id,name,created_at)`，unique `(user_id,lower(name))`。
- `task_tags(task_id,tag_id,user_id)`、`capture_tags(capture_id,tag_id,user_id)`、
  `post_tags(post_id,tag_id,user_id)`，复合 PK；触发器或服务校验关联实体归属相同用户。
- AI 建议标签先放入 `capture_ai_tags(capture_id,tag_name,confidence,llm_log_id,accepted_at,
  rejected_at)`；用户接受后才进入正式 tags/capture_tags。

### entity_relations

`id, user_id, source_type, source_id, target_type, target_id, relation_type, metadata_json,
created_at, deleted_at`。

支持 `derived_from,related_to,converted_to,material_for,generated_by,duplicate_of`。唯一约束
`(user_id,source_type,source_id,target_type,target_id,relation_type)`；服务校验两端存在且同用户。

### notifications / notification_deliveries

- `notifications(id,user_id,type,title,body,entity_type,entity_id,status(unread,read,archived),
  created_at,read_at)`。
- `notification_deliveries(id,user_id,notification_id,reminder_id,channel,provider_message_id,
  status(pending,sending,sent,failed),attempt_no,last_error,sent_at,created_at)`。
- unique `(notification_id,channel,attempt_no)`；不把 provider 的临时错误写入通知正文。

### async_jobs / async_job_events

`id, user_id, job_type, entity_type, entity_id, status, priority, progress, current_step,
result_json, error_code, error_message, retry_count, max_retries, idempotency_key,
celery_task_id, trace_id, cancel_requested_at, created_at, queued_at, started_at, updated_at,
finished_at`。

`async_job_events(id bigint identity, user_id, job_id, job_version, event_type, payload_json,
created_at)` 是追加式 SSE 重放日志。Job 状态更新与对应 event 在同一事务写入；索引
`(user_id,id)` 和 `(job_id,id)`。按保留期清理旧事件后，无效游标回退到 `jobs.snapshot`。

状态：`pending -> queued -> processing -> completed|failed|waiting_user|cancelled`；
`waiting_user -> completed|cancelled`；retry 由 failed 回到 queued 并递增。唯一约束
`(user_id,idempotency_key)`；progress 0..100 且不能倒退（新 retry 重置时记录 attempt）。

### llm_scenario_configs / llm_logs

- `llm_scenario_configs(id,scenario,provider_key,model,prompt_version,temperature,max_tokens,
  schema_version,timeout_seconds,max_retries,cache_policy,enabled,updated_at)`；不存 Provider 密钥。
- `llm_logs(id,user_id,scenario,provider_key,model,prompt_version,schema_version,input_tokens,
  output_tokens,duration_ms,cost_amount,cost_currency,status,entity_type,entity_id,trace_id,
  error_code,error_message,created_at)`。
- 输入/输出正文默认不入日志；诊断采样必须显式启用、脱敏并设短保留期。

### outbox_events / consumer_receipts / idempotency_records

- `outbox_events(id,event_type,event_version,aggregate_type,aggregate_id,user_id,payload_json,
  status(pending,publishing,published,failed),retry_count,next_attempt_at,trace_id,created_at,
  locked_by,locked_until,published_at,last_error)`。
- 索引 `(status,next_attempt_at,created_at)`；publisher 用 `FOR UPDATE SKIP LOCKED` 小批 claim。
- `consumer_receipts(consumer_name,event_id,processed_at,result_ref)` 复合 PK，作为消费幂等屏障。
- `idempotency_records(idempotency_key,handler,status(processing,completed,failed),locked_until,
  attempt_count,result_ref,last_error,created_at,updated_at)` 以复合 PK `(handler,idempotency_key)`
  保护跨重试业务效果；Redis 锁只减少并发，不能替代本表和业务唯一约束。
- payload 受按 event_type/version 的应用 Schema 校验；禁止二进制、秘密和无界正文。

### search_documents

`id, user_id, entity_type, entity_id, title, body, tags_text, category_text, metadata_text,
document_tsv, thumbnail_asset_id, entity_updated_at, indexed_at`。

唯一 `(user_id,entity_type,entity_id)`；GIN index `document_tsv`，附加 B-tree `(user_id,entity_type)`。
公开博客使用独立公共查询条件，绝不因 search document 存在而绕过 post.status。

### activity_logs

`id, user_id, actor_type(user,system,ai), action, entity_type, entity_id, before_summary_json,
after_summary_json, trace_id, created_at`。只保存恢复/审计所需摘要，不保存密码、token 或对象正文。

## 3. 关系与删除策略

- User 1:N 拥有所有业务实体；删除/禁用用户为管理员显式操作，MVP 不提供前台硬删除账户。
- Task 1:N Reminder；Habit 1:N HabitLog 且可生成 Task；Capture 1:N CaptureAsset；Post 1:N Revision。
- 多对多标签通过显式 join 表；跨领域关系只使用 entity_relations，不添加互相依赖的 nullable FK。
- 删除 Task/Habit/Capture/Post 先软删除并取消相关未执行提醒/job；Outbox 产生相应 deleted 事件。
- 资产在引用计数归零并超过保留期后异步删除；删除失败生成 maintenance job，不回滚用户的删除意图。
- Outbox、activity、notification delivery 和 llm usage 按部署保留策略清理；业务对象备份恢复必须保持 ID。

## 4. 关键状态机

### Capture processing

`pending -> processing -> ready|needs_input|failed`；failed 可 retry 回 processing。删除后任何完成消息因
实体版本/软删除检查被忽略，不能恢复内容。

### Voice record

`uploaded -> transcribing -> parsing -> waiting_user -> confirmed|discarded`；任一步可 failed；retry 从
最近成功检查点继续。confirmed 不允许再次创建正式实体。

### Post

`draft <-> private -> published -> private`。公开/取消公开均创建活动与 outbox；deleted 只能从非公开
状态进入，公开文章删除前先取消公开。

### Recurring plain tasks（普通重复任务）

- 模板任务：`recurrence_rule` 非空、`recurrence_parent_id` 为空、`occurrence_date` 为空。模板本身
  不出现在今日/日历执行视图中，只作为生成来源。
- 实例任务：由 `schedule` 队列的每日生成命令创建，`recurrence_parent_id` 指向模板，
  `occurrence_date` 为用户时区下的本地日期，`source_type='task_recurrence'`、`source_id=模板 ID`。
- 生成窗口：Beat 每日按用户时区发出一次生成命令，最多向前生成 `RECURRENCE_LOOKAHEAD_DAYS`
  （默认 1 天，可配置到 7 天）。生成命令的幂等键为 `task_recurrence:{template_id}:{local_date}`。
- 去重：唯一约束 `(user_id, recurrence_parent_id, occurrence_date)` 是最终保证；重复投递、Beat 重启
  和手动补生成都只产生一个实例。已软删除的实例不会被重新生成（唯一索引包含软删除行）。
- 执行规则：实例是普通任务，可独立完成、编辑、排期和删除，不回写模板。修改模板的
  `recurrence_rule` 只影响之后生成的实例；暂停/软删除模板后停止生成，已生成实例保留。
- 固定事件模板生成的实例继承 `is_fixed=true`、`is_ai_adjustable=false`，同样不可被 AI 移动。

### Reminder delivery

`scheduled -> claimed -> sent|failed|cancelled`；claimed 超时可由补偿任务重新入队，幂等键防止重复通知。

## 5. 迁移顺序

1. 扩展（citext）与 users/refresh_sessions。
2. categories/tags、tasks/reminders、habits/habit_logs。
3. uploads/captures/assets/voice。
4. posts/revisions/relations。
5. notifications/deliveries、async_jobs、llm configs/logs。
6. outbox/consumer receipts/activity logs/search documents/schedule previews。
7. GIN/部分索引、唯一约束和数据回填；大索引在生产升级时使用并发创建策略。

每个迁移包含 downgrade 或明确的不可逆说明；破坏性列删除采用“扩展 → 双写/回填 → 切换 → 收缩”。
