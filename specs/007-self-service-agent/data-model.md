# Phase 1 Data Model: 自助式问答与任务执行 Agent

**Feature**: 007-self-service-agent | **Date**: 2026-08-06 | **Migration**: `0019_agent_runtime`（当前最新为 `0018_blog_timeline_wordcloud_indexes`）

## 硬约束（源自 Phase 0）

1. **AgentTask 与 AsyncJob 一一对应**（R-002）：`async_job_events.job_id` 为 NOT NULL 外键，任何走现有 SSE 通道的事件都必须挂在一个 Job 上。
2. **任何表都不得对业务实体建立外键**（R-006）：`clear_completed_jobs()` 删除 Job 时会级联清理本特性的全部记录。若 `ExecutionRecord` 对 `posts.id` 建外键，用户"清空已完成任务"会连带删除文章。**这是本数据模型最容易犯且后果最严重的错误。** 业务对象一律以无外键约束的 UUID 值 + 类型字符串引用。
3. **Agent 定义不落库于本特性**（spec D-002）：`agent_runs` 只存 006 中该 Agent 的标识与绑定版本快照，不复制其配置内容。

---

## 实体

### `agent_tasks`

一次用户请求的顶层执行单元。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | 对外的 `task_id` |
| `user_id` | UUID | FK `users.id` ON DELETE CASCADE, NOT NULL | 归属 |
| `job_id` | UUID | FK `async_jobs.id` ON DELETE CASCADE, NOT NULL, UNIQUE | 一一对应（R-002） |
| `request_text` | Text | NOT NULL | 用户原始自然语言请求 |
| `intent_key` | String(64) | NOT NULL | 意图注册表键（非枚举，支持扩展，FR-048） |
| `status` | String(24) | NOT NULL | 见状态机 |
| `scope_json` | JSONB | NOT NULL, default `{}` | ConversationScope 快照：上轮对象 ID、查询条件、排序 |
| `result_summary` | Text | NULL | 最终结论摘要 |
| `created_at` / `updated_at` / `finished_at` | timestamptz | | |

**索引**：`(user_id, created_at DESC)`、`job_id` UNIQUE

**状态机**：`pending → running → (waiting_confirmation ⇄ running) → success | partial_success | failed`

`waiting_confirmation` 可与 `running` 往返：一批确认完成后继续执行下一批。

---

### `agent_runs`

任务内一个 Agent 的一次运行实例。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | 对外的 `agent_id` |
| `task_id` | UUID | FK `agent_tasks.id` ON DELETE CASCADE, NOT NULL | |
| `parent_run_id` | UUID | FK `agent_runs.id` ON DELETE CASCADE, NULL | 主控 → 子 Agent |
| `agent_key` | String(64) | NOT NULL | 006 中的 Agent 标识 |
| `agent_version` | String(64) | NOT NULL | **提交时绑定的 006 生效版本**（FR-046）；006 后续改版不影响本次运行 |
| `agent_name` | String(120) | NOT NULL | 展示名，取自 006 绑定版本的快照 |
| `responsibility` | Text | NOT NULL | 职责，同上 |
| `current_task` | Text | NOT NULL | 本次具体任务 |
| `input_scope_json` | JSONB | NOT NULL, default `{}` | 处理对象范围 |
| `allowed_tools` | JSONB | NOT NULL, default `[]` | 允许调用的工具名列表 |
| `expected_output` | Text | NULL | |
| `allow_write` | Boolean | NOT NULL, default `false` | **默认只读** |
| `status` | String(24) | NOT NULL | `pending`/`running`/`waiting_confirmation`/`success`/`partial_success`/`failed`/`skipped`（FR-026） |
| `current_tool` | String(120) | NULL | |
| `progress_current` / `progress_total` | Integer | NULL | 均为 NULL 时前端展示阶段描述而非进度条（FR-027） |
| `stage_label` | String(120) | NULL | 总量不可知时的阶段描述 |
| `result_summary` | Text | NULL | |
| `error_message` | Text | NULL | |
| `started_at` / `finished_at` | timestamptz | NULL | |

**索引**：`(task_id, started_at)`、`parent_run_id`

**约束**：`allow_write = true` 的 run 必须存在对应的已批准 `pending_writes` 记录才能执行写入（应用层强制 + integration 测试覆盖）。

---

### `agent_execution_records`

每次工具/接口/子 Agent 调用的审计条目（FR-029）。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BigInteger | PK autoincrement | |
| `task_id` | UUID | FK `agent_tasks.id` ON DELETE CASCADE, NOT NULL | |
| `run_id` | UUID | FK `agent_runs.id` ON DELETE CASCADE, NULL | |
| `step_id` | String(64) | NOT NULL | 任务内步骤标识 |
| `agent_name` | String(120) | NOT NULL | 冗余存储，便于记录独立可读 |
| `step_label` | String(200) | NOT NULL | 执行步骤描述 |
| `tool_name` | String(120) | NOT NULL | |
| `operation_type` | String(16) | NOT NULL | `query`/`analyze`/`create`/`update`/`delete`/`publish`/`rollback`（FR-030） |
| `params_digest_json` | JSONB | NOT NULL, default `{}` | **脱敏后**的参数摘要（FR-031） |
| `result_summary` | Text | NULL | 返回数量或结果摘要 |
| `status` | String(16) | NOT NULL | `success`/`failed`/`skipped` |
| `error_reason` | Text | NULL | |
| `started_at` / `finished_at` | timestamptz | NOT NULL / NULL | |
| `duration_ms` | Integer | NULL | |

**索引**：`(task_id, id)`

> ⚠️ **无业务实体外键**。被操作的对象以 `params_digest_json` 内的 UUID 值记录，不建 FK（硬约束 2）。

**脱敏规则**（写入前强制）：键名匹配 `password`/`token`/`secret`/`api_key`/`cookie`/`authorization`/`private_key`（大小写不敏感、含下划线与连字符变体）的值一律替换为 `"[redacted]"`；值形如 JWT（`eyJ` 前缀）或 `Bearer ` 前缀的字符串同样替换。

---

### `agent_pending_writes`

生成完毕但尚未落库的变更（FR-021~024）。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | 对外的 `confirmation_id` |
| `task_id` | UUID | FK `agent_tasks.id` ON DELETE CASCADE, NOT NULL | |
| `run_id` | UUID | FK `agent_runs.id` ON DELETE CASCADE, NULL | |
| `operation_type` | String(16) | NOT NULL | 同上枚举 |
| `target_type` | String(40) | NOT NULL | 如 `post` |
| `targets_json` | JSONB | NOT NULL | 目标对象 ID 与各自的乐观版本号 |
| `preview_json` | JSONB | NOT NULL | 变更预览 |
| `affected_count` | Integer | NOT NULL | 预计影响条数 |
| `reversible` | Boolean | NOT NULL | 是否支持回滚 |
| `high_risk` | Boolean | NOT NULL | 删除/覆盖/批量更新为 true，需二次确认（FR-023） |
| `decision` | String(16) | NOT NULL, default `pending` | `pending`/`approved`/`rejected`/`expired` |
| `decided_at` | timestamptz | NULL | |
| `created_at` | timestamptz | NOT NULL | |

**索引**：`(task_id, decision)`

**不变式**：`decision != 'approved'` 时，任何写入路径均不得执行（security 测试专项覆盖）。`targets_json` 中的版本号在实际写入时由既有领域服务重新校验，版本不匹配即冲突失败而非静默覆盖。

---

## 与既有表的关系

```text
users ──┬── async_jobs ──── async_job_events        （既有；SSE 事实源）
        │        │
        │        └──1:1── agent_tasks               （新增）
        │                     ├──1:N── agent_runs
        │                     ├──1:N── agent_execution_records
        │                     └──1:N── agent_pending_writes
        │
        └── posts / captures / tasks ...             （业务实体：仅以 UUID 值引用，无 FK）
```

`clear_completed_jobs()` 删除 `async_jobs` 行 → 级联清除 `agent_tasks` 及其全部子表 → 业务实体不受影响（R-006）。

## 状态与事件的映射

`agent_runs` 的任一字段变更 → 构造一条 `agent.status_changed` 事件写入 `async_job_events`（与业务变更同事务，遵循既有 "written in the same transaction as job updates" 约定）→ 经既有 `/events/jobs` SSE 推送。

`event_type` 取值 `agent.status_changed`（20 字符，满足 `String(40)` 限制）。

## 配置项

| 配置 | 默认 | 上限 | 出处 |
|---|---|---|---|
| `AGENT_MAX_BATCH_OBJECTS` | 200 | 500 | R-005 |
| `AGENT_MAX_CONCURRENCY` | 4 | 8 | R-005 |
