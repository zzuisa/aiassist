# Agent Orchestration API Contract

Base path: `/api/v1/agent`

## Capability and plan views

### GET `/capabilities`

返回当前用户的安全能力视图。模型/前端只看到平台安全名、职责、输入/输出契约、风险、权限和可用性；响应不包含 provider 原名映射、connection ID、端点、凭据或 server instructions。

### GET `/conversations/{conversation_id}/plans?scope=current`

默认 `scope=current`，仅返回当前活动计划或最近一个与当前会话轮次相关的终态计划。`scope=recent&limit=N` 由用户显式请求历史时使用。响应为 `agent-plan-view.v2`。

### GET `/plans/{plan_id}`

返回所有者的完整有界计划视图，但不返回静态参数、原始产物、正文或连接信息。

### POST `/plans/{plan_id}/retry`

```json
{"mode":"failed_chain"}
```

只恢复可安全重试的 failed/stalled Graph node 或 operator；通过 LangGraph `Command`/resume 从最新 checkpoint 继续，保留旧 attempts、artifacts 和已经验证的业务结果。ambiguous 外部写必须先验证，不能直接重发。该接口不创建第二个计划或自研步骤队列。

### POST `/plans/{plan_id}/cancel`

向 LangGraph Graph Run 发出取消命令，停止尚未开始的工作和可中断的后续批次。已确认并已经发生的业务效果不回滚、不伪装为未执行；报告清楚列出已完成和未处理范围。

## Mutation preview and confirmation

### GET `/tasks/{task_id}/confirmations/{confirmation_id}`

返回 `mutation-preview.v2`。列表详情支持分页，公共计划 SSE 只包含 confirmation reference 和数量。

### POST `/tasks/{task_id}/confirmations/{confirmation_id}`

```json
{
  "decision": "approve",
  "preview_digest": "64-char-sha256"
}
```

`decision` 为 `approve | reject`。批准必须匹配当前未过期 preview digest；事务只记录决定和异步命令，不同步执行批量 MCP。重复同一决定幂等，不同 digest 返回 409。

## Report

### GET `/plans/{plan_id}/report`

返回最新 ready `task-report.v1`。报告私有且只允许计划所有者访问。

### POST `/plans/{plan_id}/report/regenerate`

创建新 report revision，只读取持久 outcomes、verification 和安全 artifacts。不得重新调用搜索、分析、业务写或验证 MCP；同 source digest 可直接复用。返回 202 和 report reference。

## Status and errors

继续复用 `/api/v1/events/jobs`，事件名仍为 `agent.plan_updated`，payload 升级为 `agent-plan-event.v2`。事件携带安全的 `graph_run_id`、runtime_state 和 Graph phase，但不携带 checkpoint payload。客户端只接受比本地更高的 projection `plan.version`，重连后以 REST/SSE 最新快照为准。

稳定错误至少包括：

- `agent_capability_gap`
- `agent_capability_drift`
- `agent_plan_schema_invalid`
- `agent_artifact_schema_invalid`
- `agent_preview_digest_mismatch`
- `agent_preview_expired`
- `agent_version_conflict`
- `agent_write_outcome_ambiguous`
- `agent_verification_failed`
- `agent_report_reconciliation_failed`

所有错误消息对用户可操作但不包含 endpoint、credential、raw provider error、Prompt 或正文。
