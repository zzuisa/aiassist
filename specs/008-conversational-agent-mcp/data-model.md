# Data Model: 对话式 Agent 与 MCP 任务路由

**Feature**: 008-conversational-agent-mcp | **Migration target**: `0020_conversational_agent`

## 1. AgentConversation

持久化的一段用户对话。

`id, user_id, title, status(active|archived), context_json, last_message_at, created_at, updated_at`

- `context_json` 只保存最近对象范围、有效查询条件、待确认 ID 和安全摘要，不保存隐藏推理或凭据。
- 索引：`(user_id, status, last_message_at DESC)`；所有读取必须过滤 `user_id`。

## 2. AgentMessage

会话中的用户、助手或系统状态消息。

`id, conversation_id, user_id, role(user|assistant|system), kind(text|clarification|result|error), content_json, client_message_id, reply_to_id, created_at`

- `(user_id, client_message_id)` 唯一，实现客户端重发幂等。
- `content_json` 使用 `conversation-message.v1` 应用校验；最大 4,000 字用户文本，工具原始结果不直接存入消息正文。
- `reply_to_id` 只能引用同一会话消息。

## 3. AgentTurn

一次用户消息从接收到回复完成的生命周期。

`id, conversation_id, user_message_id, assistant_message_id, job_id, agent_task_id, status, route_kind, current_step, retry_of_id, retry_count, last_heartbeat_at, error_code, error_message, created_at, finished_at`

状态：`accepted -> routing -> waiting_clarification | executing | waiting_confirmation | success | partial_success | failed | stalled | cancelled`。

- 每个用户消息恰好一个原始 Turn；重试创建新 Turn 并通过 `retry_of_id` 关联。
- `job_id` 唯一且必填；`agent_task_id` 仅任务型消息存在。
- 终态：`success, partial_success, failed, stalled, cancelled`。

## 4. AgentRoutingDecision

结构化、可审计的路由事实，不包含思维链。

`id, turn_id, schema_version, attempt, route_kind, objective, operation_type, target_scope_json, semantic_args_json, candidate_tools_json, selected_tool, requires_confirmation, confidence, validation_status, validation_errors_json, created_at`

- `(turn_id, attempt)` 唯一。
- `candidate_tools_json` 只含安全 tool key；不得保存 endpoint 或服务器 instructions。
- `selected_tool` 必须在该 Turn 的候选列表中且当前 grant 有效。

## 5. McpConnection

外部 MCP 服务的非敏感注册信息。

`id, user_id, config_key, display_name, transport, enabled, health_status, protocol_version, catalog_etag, catalog_expires_at, last_checked_at, last_error_code, created_at, updated_at`

- `(user_id, config_key)` 唯一；`config_key` 解析只读 secret 配置，不得包含 URL、token 或 connection string。
- `transport` 首版只能为 `streamable_http`。
- 状态：`unknown, healthy, degraded, unavailable, disabled`。

## 6. McpToolSnapshot

最近一次发现到的安全工具清单。

`id, connection_id, tool_key, remote_name, responsibility, tool_type, input_schema_json, output_schema_json, risk_json, available, unavailable_reason, catalog_version, discovered_at`

- `(connection_id, tool_key, catalog_version)` 唯一。
- schema 必须是可接受的 JSON Schema 2020-12 子集；无法规范化时 `available=false`。
- 不保存 remote server instructions、端点、认证头或返回样本。

## 7. McpToolGrant

用户对具体 MCP 工具的最小权限授权。

`id, user_id, connection_id, tool_key, allowed, allowed_operations_json, scope_json, granted_at, revoked_at, updated_at`

- `(user_id, connection_id, tool_key)` 唯一。
- grant 必须同时满足 connection ownership、tool availability 和当前业务对象 ownership。
- 撤销立即生效；批准 PendingWrite 不冻结或绕过 grant。

## Relationships

```text
User 1 ── * AgentConversation 1 ── * AgentMessage
                         │
                         └── 1 ── * AgentTurn 1 ── * AgentRoutingDecision
                                             ├── 0..1 AgentTask
                                             └── 1 AsyncJob

User 1 ── * McpConnection 1 ── * McpToolSnapshot
  └──────────────────────────── * McpToolGrant
```

## Transaction Boundaries

1. **Accept message**: message + turn + job + activity + outbox commit together。
2. **Route**: routing decision + turn state + execution record/status event commit together。
3. **Tool result**: execution record + assistant message + scope update + terminal states commit together。
4. **Pending write**: existing PendingWrite + turn/task/job `waiting_confirmation` commit together；业务表零变更。
5. **Approved write**: recheck grant/ownership/version + external/internal effect record + terminal states commit together where local transaction permits；外部调用以 idempotency key 和补偿记录处理。

## Retention and Deletion

- 归档会话不删除消息或业务对象。
- 删除 Job 历史时只级联 Turn 的运行记录，不级联文章、任务、日历或外部对象。
- MCP connection 删除只撤销本地 grant 和 snapshot；不调用远端删除。
- 审计记录按现有 Job 保留规则；敏感配置始终不在数据库备份范围。
