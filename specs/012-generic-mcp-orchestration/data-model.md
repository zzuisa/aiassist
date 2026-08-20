# Data Model: 通用 MCP 任务编排与报告

## Existing entities retained

继续复用 `AgentTask`、`AgentRun`、`ExecutionRecord`、`AgentExecutionPlan`、`AgentPlanStep`、`AgentStepDependency`、`AgentStepArtifact`、`AgentStepAttempt`、`PendingWrite`、`AgentTurn`、`AsyncJob` 和 `AsyncJobEvent`。012 通过增量迁移扩展 011 数据，不删除历史计划或业务对象。011 的计划表在 012 中是用户/审计投影；LangGraph PostgreSQL Checkpointer 是唯一运行时图状态真相。

## LangGraph Runtime State

LangGraph 运行时使用 PostgreSQL Checkpointer 的 `thread_id = plan_id` 保存 Graph State、super-step、pending writes、interrupt 和恢复位置。Checkpointer 的官方表由 LangGraph 迁移管理，不与业务表混用 JSONB。

Graph State 只允许保存有界引用和结构化结果：

- `plan_id`, `trace_id`, `capability_snapshot_id`
- 当前固定 graph phase 和已完成 operator keys
- artifact IDs/digests、batch cursor 和 aggregate counters
- `pending_confirmation_id` 或 clarify reference
- graph run status 和安全错误码

Graph State 不保存 Prompt、chain-of-thought、凭据、端点、原始正文或未裁剪 MCP payload。业务对象逐项 outcome 仍写入 AI Assist 表，不能只留在 checkpoint。

## AgentCapabilitySnapshot

一次任务在规划前冻结的安全能力集合。

- `id`: UUID
- `task_id`: 唯一关联 AgentTask
- `user_id`: 所有者
- `schema_version`: `capability-snapshot.v1`
- `manifest_version`: 来源 safe manifest 版本
- `content_digest`: 规范化安全清单 SHA-256
- `capability_count`: 0..100
- `created_at`

计划必须绑定一个快照；旧 011 计划迁移时可暂时为空并标 legacy，不反向伪造历史能力。

## AgentCapabilitySnapshotItem

快照中的一个不可变能力定义。

- `id`, `snapshot_id`
- `safe_name`: 模型可见名称，`^[A-Za-z0-9_-]{1,64}$`
- `source`: `internal_api | mcp`
- `definition_version`, `catalog_version`
- `tool_type`: `read | write`
- `responsibility`
- `input_schema_json`, `output_schema_json`
- `risk_json`, `required_permission`
- `available`, `unavailable_reason`
- `connection_id`: MCP 私有绑定，可空
- `provider_tool_key`: 远端原名，仅后端可见
- `timeout_seconds`, `max_retries`
- `idempotency_mode`: `none | supported | required`
- `verification_mode`: `none | read_back | required`
- `created_at`

唯一约束：`(snapshot_id, safe_name)`。不得保存端点、凭据、服务器 instructions 或连接字符串。

## AgentExecutionPlan additions

- `capability_snapshot_id`: 关联冻结快照
- `graph_thread_id`: LangGraph thread ID，唯一且等于 plan ID 的字符串表示
- `graph_run_id`: 当前/最近一次 Graph Run 的安全引用
- `runtime_state`: `checkpointed | running | interrupted | completed | failed`
- `phase`: `planning | executing | waiting_confirmation | verifying | reporting | complete`
- 现有 `version` 明确定义为单调 `state_version`，不表示可变 plan revision
- `verified_count`, `conflict_count`, `unprocessed_count`, `waiting_count`

旧 `status` 保持兼容；phase 用于更精确的紧凑 UI。旧 scheduler 不再领取或推进这些行；Graph node 在事务中更新投影并发布 SSE。

## AgentPlanStep additions

- `capability_snapshot_item_id`: 可空；平台 operator 没有外部 capability 时为空
- `step_kind`: `select | map | filter | aggregate | analyze | mutate | verify | report`
- `input_bindings_json`: 仅引用直接依赖的 artifact key、contract 和受限 JSON Pointer
- `output_contract`: artifact contract ID/version
- `scope_policy_json`: 允许的对象类型和是否可扩张范围
- `batch_policy_json`: `max_items <= 1000`、`page_size <= 100`、`max_concurrency <= 4`
- `failure_policy`: `block_dependents | continue_partial | always_finalize`
- `generation`: 重试代际，保留旧 attempts/artifacts

状态沿用 011；mutate 在批准后通过 Graph resume 继续，verify/report 是固定 Graph node，不再通过自研 ready-step 队列推进。

## AgentStepWorkItem

步骤内部可恢复的批次/逐项工作状态。

- `id`, `plan_id`, `step_id`, `generation`
- `chunk_no`, `ordinal`, `object_key`
- `expected_version`
- `status`: `pending | queued | running | succeeded | conflict | failed | skipped | unknown`
- `attempt_count`, `logical_operation_key`
- `input_digest`, `output_digest`
- `error_code`, `retryable`
- `lease_until`, `started_at`, `finished_at`, `created_at`, `updated_at`

唯一约束：`(step_id, generation, object_key)` 和 `logical_operation_key`。一个可见步骤可拥有多个 chunk，但 UI 只显示聚合计数。

## AgentStepArtifact additions

- `artifact_key`, `sequence`, `generation`
- `producer_attempt_id`
- `item_count`, `byte_size`, `truncated`
- `validation_status`: `valid | invalid`
- `is_terminal`

唯一约束：`(step_id, generation, artifact_key, sequence)`。每个 chunk 默认最多 100 项，并受 MCP/应用字节限制。产物保存安全结构化值、对象 ID/版本和 provenance，不保存正文或原始 provider payload。

## AgentStepAttempt additions

- `capability_snapshot_item_id`
- `logical_operation_key`: 跨投递/重试稳定的业务 effect key
- `delivery_event_id`, `worker_task_id`
- `arguments_digest`, `input_digest`, `result_digest`
- `outcome`: `running | success | failed | timeout | conflict | cancelled | ambiguous`
- `lease_until`, `sanitized_error_json`

现有 `idempotency_key` 继续标识单次 attempt/delivery；业务防重使用 logical_operation_key，二者不能混用。

## PendingWrite additions (Mutation Preview)

- `user_id`, `plan_id`, `step_id`
- `schema_version`: `mutation-preview.v2`
- `preview_version`, `preview_digest`, `source_artifact_digest`
- `capability_snapshot_item_id`
- `apply_status`: `not_started | queued | applying | applied | partial | failed`
- `expires_at`, `confirmed_by_user_id`, `confirmed_at`, `confirmed_digest`
- `operation_key`

现有 `decision` 保持 `pending | approved | rejected | expired`。批准请求必须携带当前 preview_digest；确认事务不执行批量写。

## AgentMutationItem

冻结预览和写入对账中的一项业务变更。

- `id`, `preview_id`, `ordinal`
- `object_type`, `object_id`, `object_title`
- `expected_version`
- `current_value_json`, `proposed_value_json`
- `confidence`, `provenance_json`, `risk_json`
- `status`: `pending | applied | conflict | failed | skipped | unknown`
- `logical_operation_key`, `applied_version`
- `error_code`, `started_at`, `finished_at`

唯一约束：`(preview_id, object_type, object_id)` 和 `logical_operation_key`。分类建议的 category ID 必须存在于前置 taxonomy artifact。

## AgentVerificationResult

对一项 mutation 的独立回读结论。

- `id`, `mutation_item_id`（唯一）
- `verification_step_id`
- `expected_state_json`, `expected_digest`
- `observed_state_json`, `observed_digest`
- `status`: `verified | mismatch | not_found | unauthorized | provider_error | unverifiable`
- `error_code`, `checked_at`

只有 `verified` 进入报告 verified success；`applied` 本身不等于成功。

## AgentTaskReport

由终态事实生成、可版本化重建的报告。

- `id`, `plan_id`, `revision`
- `schema_version`: `task-report.v1`
- `source_digest`: 所有 terminal outcome/verification 的规范化摘要
- `status`: `generating | ready | failed`
- `totals_json`, `facts_json`
- `markdown`, `short_summary`
- `generation_method`: `deterministic | llm_enhanced`
- `validation_status`: `valid | invalid`
- `error_code`, `created_at`

唯一约束：`(plan_id, revision)`；相同 source_digest 可直接复用 ready 报告。报告重建只读取事实表和安全产物。

## State transitions

```text
Graph phase:
planning -> executing -> waiting_confirmation -> executing
executing -> verifying -> reporting -> complete
任何 node -> failed（LangGraph retry policy 用尽后）

Mutation preview:
pending -> approved -> queued -> applying -> applied | partial | failed
pending -> rejected | expired

Mutation item:
pending -> applied -> verified (via AgentVerificationResult)
pending -> conflict | failed | skipped
running/timeout -> unknown -> verified | mismatch | unverifiable

Report:
generating -> ready | failed
ready -> new revision generating (regenerate; no business execution)
```

版本冲突终止该 item 的写入，不触发 destructive capability。mutation、verification 和 report 的部分失败不删除已完成 sibling 结果。

## Relationships

```text
AgentTask 1 ── 1 AgentCapabilitySnapshot 1 ── * AgentCapabilitySnapshotItem
AgentExecutionPlan 1 ── 1 LangGraph Runtime State (thread/checkpoint)
AgentExecutionPlan * ── 1 AgentCapabilitySnapshot
AgentExecutionPlan 1 ── * AgentPlanStep 1 ── * AgentStepWorkItem
AgentPlanStep      1 ── * AgentStepArtifact
AgentPlanStep      1 ── * AgentStepAttempt
AgentPlanStep      0..1 ── 1 PendingWrite 1 ── * AgentMutationItem
AgentMutationItem  1 ── 0..1 AgentVerificationResult
AgentExecutionPlan 1 ── * AgentTaskReport
```

## Migration and retention

- 新迁移基于现有 0023，先建业务投影表/可空列并安装 LangGraph PostgreSQL Checkpointer schema；回填 legacy 标记，再对 012 新计划在服务层强制快照绑定；不为历史计划伪造工具权限。
- Graph Checkpointer schema 的升级由 LangGraph 官方迁移流程执行并锁定版本；业务 Alembic 迁移只保存 thread/run 引用，不复制 checkpoint 表。
- 删除用户/任务时编排审计数据级联删除；删除会话不触碰博客文章。
- 计划表只保存业务对象 ID/版本，不建立会导致业务内容级联删除的外键。
- 验证空库升级、0023→0024 存量升级、downgrade 和 `alembic check`。
