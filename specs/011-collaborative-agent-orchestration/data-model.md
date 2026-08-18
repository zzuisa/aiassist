# Data Model: 对话式协作 Agent 调度

## AgentExecutionPlan

一轮任务的持久执行图。纯聊天轮次不创建。

字段：

- `id`: UUID 主键
- `user_id`: 所有者
- `task_id`: 唯一关联 `AgentTask`
- `turn_id`: 可空且唯一关联会话 `AgentTurn`，旧任务入口为空
- `schema_version`: `agent-task-plan.v1`
- `objective`: 用户可见目标，最长 500
- `status`: `planning | pending | running | waiting_user | success | partial_success | failed | stalled | cancelled`
- `version`: 单调递增整数，用于事件乱序保护
- `step_count`: 1..12
- `completed_count`, `failed_count`, `skipped_count`: 非负聚合计数
- `result_summary`: 安全终态摘要，最长 4000
- `error_code`, `error_message`, `error_retryable`: 稳定错误信息
- `started_at`, `finished_at`, `created_at`, `updated_at`

约束：一个 Task 至多一个计划；一个 Turn 至多一个计划；所有状态转换增加 `version`。

## AgentPlanStep

计划中的一个可调度工作单元。

字段：

- `id`: UUID 主键
- `plan_id`: 所属计划
- `step_key`: 计划内稳定键，格式 `step_[a-z0-9_]+`
- `position`: 原计划展示顺序
- `title`: 用户可见短标题
- `responsibility`: 安全职责说明
- `agent_key`, `agent_name`, `agent_version`: 平台解析的 Agent 绑定
- `tool_name`: 已注册工具键
- `operation_type`: query/analyze/create/update/delete/publish/rollback/external_effect
- `arguments_json`: 经过校验的静态参数，不保存凭据
- `input_source`: `current_message | conversation_context | dependency`
- `expected_output`: 用户可见预期产物
- `requires_confirmation`: 写步骤必须为 true
- `status`: `pending | queued | running | waiting_confirmation | success | partial_success | failed | blocked | skipped | stalled | cancelled`
- `progress_current`, `progress_total`, `stage_label`
- `attempt_count`: 0..2
- `result_summary`, `error_code`, `error_message`, `error_retryable`
- `run_id`: 可空关联当前 `AgentRun`
- `queued_at`, `started_at`, `finished_at`, `created_at`, `updated_at`

唯一约束：`(plan_id, step_key)`、`(plan_id, position)`。

状态转换：

```text
pending -> queued -> running -> success | partial_success | failed
pending -> blocked | skipped | cancelled
running -> waiting_confirmation -> running -> success | failed
queued/running -> stalled
failed/stalled -> queued 仅由显式安全重试触发
```

## AgentStepDependency

步骤间的有向边。

- `plan_id`
- `step_id`
- `depends_on_step_id`
- `accepted_statuses_json`: 默认 `['success','partial_success']`

唯一约束：`(step_id, depends_on_step_id)`；禁止自环。计划激活前执行全图无环与深度校验。

## AgentStepArtifact

步骤输出的最小协作产物。

- `id`: UUID
- `plan_id`, `step_id`
- `artifact_type`: `object_scope | tool_result | analysis_proposals | write_preview | final_fragment`
- `schema_version`: 对应产物 Schema
- `payload_json`: 大小受限的结构化内容
- `object_scope_json`: 对象类型、ID、版本和来源
- `content_digest`: 用于幂等和新鲜度判断
- `created_at`

约束：不得保存 Prompt、Skill 指令、推理、凭据、连接信息或未裁剪原始 MCP 响应。正文不作为协作产物保存。

## AgentStepAttempt

步骤的一次执行尝试。

- `id`: UUID
- `step_id`
- `attempt_number`: 1..2
- `idempotency_key`: 全局唯一
- `status`: `running | success | failed`
- `error_code`, `error_retryable`
- `started_at`, `finished_at`, `duration_ms`

唯一约束：`(step_id, attempt_number)` 和 `idempotency_key`。

## Relationships

```text
AgentConversation 1 ── * AgentTurn 0..1 ── 1 AgentExecutionPlan
AgentTask         1 ── 1 AgentExecutionPlan
AgentExecutionPlan 1 ── * AgentPlanStep
AgentPlanStep      * ── * AgentPlanStep through AgentStepDependency
AgentPlanStep      1 ── * AgentStepArtifact
AgentPlanStep      1 ── * AgentStepAttempt
AgentPlanStep      0..1 ── 1 AgentRun
AgentPlanStep      0..1 ── * PendingWrite through AgentRun
```

## Retention and Ownership

- 删除用户时全部级联删除。
- 删除会话时计划随 Turn 删除，但业务对象不受影响。
- 删除 AgentTask 时计划级联删除；计划表不持有业务对象外键。
- 所有读取先通过计划的 `user_id` 过滤；步骤和产物只能经所有者计划访问。

