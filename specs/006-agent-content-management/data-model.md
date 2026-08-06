# Data Model: 博客 Agent 内容管理

## Modeling Principles

1. 系统 manifest 是运行拓扑与锁定安全规则真相，不由用户数据修改。
2. Agent 用户内容只追加版本；激活是单独、带并发控制的指针。
3. 正式任务固定配置与运行选择结果分离，历史不读取当前配置。
4. Blog Skill 继续使用现有实体；只通过 ID/版本引用。
5. 预览输入在异步派发前持久化，消息不携带正文或 Prompt。

## System Agent Manifest (code-owned)

不是数据库表。每个发布版本包含：

| Field | Type | Rules |
|---|---|---|
| `manifest_version` | string | 单调发布标识，如 `blog-agents.1` |
| `agent_key` | string | 稳定、唯一、`^[a-z][a-z0-9-]{1,63}$` |
| `node_type` | enum | `stage/orchestrator/agent/capability/validator/persistence` |
| `stage/order` | string/int | 自动布局与执行排序 |
| `execution_mode` | enum | `required/conditional/readonly` |
| `editable_fields` | string[] | 用户配置 allowlist |
| `required_capabilities` | string[] | 安全能力标识 |
| `skip_policy` | enum | `skip/degrade/block` |
| `default_config` | object | 通过 `blog-agent-config.v1` |
| `locked_policy_refs` | string[] | 安全底座引用，不含密钥 |
| `incoming/outgoing` | edge[] | 引用已知节点且全图无环 |

启动和契约测试保证每条可到达的生产路径都经过 validator 与 candidate-save。

## BlogAgentVersion (`blog_agent_versions`)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | Owner FK, required |
| `agent_key` | string(64) | 必须存在于创建时 manifest |
| `version_number` | integer | 正整数，用户/Agent 内单调唯一 |
| `schema_version` | string | `blog-agent-config.v1` |
| `base_manifest_version` | string(48) | 创建时系统清单版本 |
| `base_default_hash` | string(64) | 创建时该 Agent 内置默认哈希 |
| `config_json` | JSONB | 完整不可变 Agent 配置 |
| `content_hash` | string(64) | 规范化配置 SHA-256 |
| `validation_json` | JSONB | 创建时结构/安全校验摘要，不含完整 Prompt |
| `change_summary` | string(500)? | 用户安全摘要 |
| `source` | enum | `user_edit/history_restore/system_default` |
| `created_at` | timestamp | Required |

Constraints/indexes:

- Unique `(user_id, agent_key, version_number)` and `(user_id, id)`.
- Config max serialized size 128 KiB; each editable instruction section max 24 KiB; total sections max 20.
- Version row is immutable after insert; database/service rejects update and only allows deletion of unreferenced, inactive drafts if retention policy permits.
- `validation_json` only contains codes, field paths, severity and hashes.

## BlogAgentActivation (`blog_agent_activations`)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | Owner FK |
| `agent_key` | string(64) | 每用户/Agent 唯一 |
| `active_version_id` | UUID? | 同 owner、同 agent_key 的版本；null 表示内置默认 |
| `enabled` | boolean | 条件 Agent 可改；必经/只读节点强制 true |
| `version` | integer | 乐观锁，每次激活/启停 +1 |
| `activated_at` | timestamp? | 最近显式激活时间 |
| `created_at/updated_at` | timestamp | Audit timestamps |

State transitions:

```text
implicit builtin ──activate user version──> active user version
       │                                      │
       └──copy system default──> draft ─validate/confirm─┘
active vN ──restore vK──> new draft vN+1 ─activate──> active vN+1
conditional enabled <──explicit impact confirmation──> conditional disabled
```

Activation transaction locks the row, checks expected `version`, version ownership/key, current manifest compatibility, dependency policy and schema, then records Activity.

## BlogOrchestrationSnapshot (`blog_orchestration_snapshots`)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | Owner FK |
| `post_ai_run_id` | UUID | Unique FK to PostAIRun |
| `async_job_id` | UUID | Unique, matches run job |
| `schema_version` | string | `blog-orchestration-snapshot.v1` |
| `manifest_version` | string | Frozen manifest |
| `safety_policy_version` | string | Frozen locked policy version |
| `orchestrator_version_ref` | JSONB | builtin/user version reference + hash |
| `eligible_agents_json` | JSONB | frozen Agent keys/version refs/enabled/dependency policy |
| `skill_version_id` | UUID | Existing BlogSkillVersion |
| `capabilities_json` | JSONB | allowlisted descriptor snapshot + hash; no endpoints/credentials |
| `configuration_hash` | string(64) | Canonical frozen configuration hash |
| `execution_result_json` | JSONB? | selected/skipped reasons, capability and quality outcomes |
| `result_recorded_at` | timestamp? | write-once result timestamp |
| `created_at` | timestamp | Same transaction as run/job/outbox |

Frozen configuration columns are immutable. `execution_result_json` may move once from null to a validated result or be idempotently replayed with the same hash; conflicting rewrites fail.

## BlogAgentPreview (`blog_agent_previews`)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | Owner FK |
| `async_job_id` | UUID | Unique FK to AsyncJob |
| `agent_key` | string(64) | Target Agent |
| `agent_version_id` | UUID? | User version; null only for explicit builtin preview |
| `sample_source` | enum | `temporary/post_revision` |
| `post_revision_id` | UUID? | Owned revision when selected |
| `sample_title` | string(240)? | Temporary private input |
| `sample_markdown` | text? | Temporary private input, max 200k |
| `input_hash` | string(64) | Idempotency/privacy diagnostics |
| `options_json` | JSONB | Bounded preview options |
| `status` | enum | `pending/queued/processing/completed/failed/cancelled` |
| `result_json` | JSONB? | Plan, selected/skipped, section names/hashes/lengths, validation, usage |
| `error_code/error_summary` | string? | Stable safe error |
| `expires_at` | timestamp? | Optional raw temporary input cleanup |
| `created_at/updated_at/completed_at` | timestamp | Lifecycle timestamps |

Exactly one input mode is valid: temporary title/markdown or owned `post_revision_id`. Result never creates PostRevision/PostAICandidate.

## Existing Entities Referenced

- `BlogSkill` / `BlogSkillVersion`: unchanged; topology references identity and task snapshot references fixed version.
- `PostAIRun`: one-to-one orchestration snapshot; legacy runs may have none.
- `AsyncJob`: preview and formal run status truth.
- `ActivityLog`: records agent version/activation/default restore actions using safe summaries.
- `OutboxEvent`: preview message and formal run dispatch in same transaction as durable input/snapshot.

## Ownership and Retention

- Every lookup begins with `user_id`; nested version/activation/preview/snapshot relationships recheck owner and agent_key.
- Agent configs and preview samples are private; no public endpoint or search indexing.
- Referenced Agent versions and formal snapshots are retained with runs. Unreferenced inactive drafts may be soft-deleted later; MVP may omit deletion UI.
- Temporary preview bodies may expire according to blog retention settings; result metadata and hashes remain for audit without reconstructing content.
- Activity/log records never store full config, prompt, article body, provider response or capability secret fields.

## Migration Sequence

1. Create `blog_agent_versions` and `blog_agent_activations` with unique/ownership indexes.
2. Create `blog_orchestration_snapshots` and `blog_agent_previews` with run/job references and status checks.
3. Add indexes `(user_id, agent_key, version_number desc)`, `(user_id, updated_at)`, `(user_id, status, created_at)`.
4. Do not seed user rows: absence intentionally resolves to manifest defaults.
5. Do not backfill old run snapshots; serialize them as `legacy_incomplete`.
6. Downgrade removes only new tables after reference-safe checks and leaves existing Skill/run/article tables untouched.
