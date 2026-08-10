# Tasks: 对话式 Agent 与 MCP 任务路由

**Input**: Design documents from `/specs/008-conversational-agent-mcp/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Tests are required by the project constitution and appear before the implementation tasks they validate.

**Organization**: Tasks are grouped by user story. The implementation baseline is `006-agent-content-management@d70e39c`; this branch must first integrate that completed self-service Agent rather than create a second runtime.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it uses different files and has no incomplete dependency
- **[Story]**: User story from spec.md
- Every task names its target file or directory

## Phase 1: Setup and Baseline Integration

**Purpose**: Bring the completed self-service Agent into this branch and prepare MCP dependencies/configuration.

- [ ] T001 Integrate `006-agent-content-management@d70e39c` self-service Agent baseline, including `backend/app/modules/agent/`, `backend/app/models/agent.py`, `backend/app/workers/tasks/agent.py`, `backend/alembic/versions/0019_agent_runtime.py`, `frontend/src/modules/agent/`, `frontend/src/components/agent/`, `frontend/src/api/agent.ts`, and `frontend/src/stores/agent.ts`
- [ ] T002 Run the baseline Agent regression suites and record the green baseline in `specs/008-conversational-agent-mcp/quickstart.md`
- [ ] T003 [P] Add the stable official MCP Python SDK 2.x constraint and type-check configuration in `backend/pyproject.toml`
- [ ] T004 [P] Add non-secret MCP settings, limits, watchdog thresholds, and secrets-file path in `backend/app/core/config.py` and `.env.example`
- [ ] T005 [P] Add a redacted Streamable HTTP connection example in `deploy/secrets/mcp-connections.example.json`
- [ ] T006 Mount the operator-provided MCP secrets file read-only into backend and heavy worker services in `compose.yaml`

**Checkpoint**: Existing `/agent` query, analysis, status, audit, and confirmation behavior passes before conversational changes begin.

---

## Phase 2: Foundational Conversation and Capability Infrastructure

**Purpose**: Blocking persistence, schemas, gateway, registry, and durable acceptance primitives used by every story.

**⚠️ CRITICAL**: No user story implementation starts until this phase is complete.

### Tests first

- [ ] T007 [P] Add migration upgrade/downgrade and cascade-safety tests for all conversation and MCP metadata tables in `backend/tests/integration/test_conversational_agent_migration.py`
- [ ] T008 [P] Add JSON Schema validation tests for route, SSE event, and safe manifest v2 contracts in `backend/tests/contract/test_conversation_schemas.py`
- [ ] T009 [P] Add configuration tests proving endpoint and token values never enter database models, manifests, logs, or validation errors in `backend/tests/security/test_mcp_secret_boundary.py`
- [ ] T010 [P] Add message-idempotency and ownership-isolation tests for the durable acceptance transaction in `backend/tests/integration/test_conversation_acceptance.py`

### Implementation

- [ ] T011 Create AgentConversation, AgentMessage, AgentTurn, AgentRoutingDecision, McpConnection, McpToolSnapshot, and McpToolGrant models with indexes and constraints in `backend/app/models/agent_conversation.py`
- [ ] T012 Register the new models for metadata discovery in `backend/app/models/__init__.py` and `backend/app/db/base.py`
- [ ] T013 Add migration `0020_conversational_agent` without business-entity foreign keys in `backend/alembic/versions/0020_conversational_agent.py`
- [ ] T014 [P] Implement Pydantic request, response, state, and structured route schemas in `backend/app/modules/agent/conversation_schemas.py`
- [ ] T015 [P] Define provider-neutral MCP connection, discovery, call, error, and result protocols in `backend/app/services/mcp/base.py`
- [ ] T016 Implement validated secrets-file loading, config-key lookup, host allowlisting, redirect validation, and secret redaction in `backend/app/services/mcp/config.py`
- [ ] T017 Implement the official SDK 2.x Streamable HTTP provider with timeouts, bounded retry, protocol compatibility, result-size limits, and stable errors in `backend/app/services/mcp/provider.py`
- [ ] T018 Implement the synchronous worker-facing McpGateway façade and dependency injection in `backend/app/services/mcp/gateway.py` and `backend/app/services/mcp/__init__.py`
- [ ] T019 Extend ToolDefinition and ToolRegistry with validated argument schemas, risk annotations, per-user grant checks, and safe manifest v2 in `backend/app/modules/agent/registry.py`
- [ ] T020 Implement atomic conversation/message/turn/job/outbox acceptance and owned lookups in `backend/app/modules/agent/conversation_service.py`
- [ ] T021 Register conversation event types and snapshot serialization without endpoint, credential, prompt, or raw MCP output fields in `backend/app/modules/agent/status.py` and `backend/app/modules/jobs/sse.py`

**Checkpoint**: Messages can be durably accepted and queried; MCP can be configured and discovered internally, but no conversational routing or tool execution is exposed yet.

---

## Phase 3: User Story 1 — Normal Conversation (Priority: P1) 🎯 MVP

**Goal**: `hi`, greetings, thanks, and “你能做什么” receive natural, truthful replies without creating business tasks or tool calls.

**Independent Test**: In a new conversation, send `hi` and `你能做什么`; both produce persisted assistant replies, no AgentTask, no ExecutionRecord, and no business mutation.

### Tests for User Story 1

- [ ] T022 [P] [US1] Add REST contract tests for create/list/get conversation and submit/list messages in `backend/tests/contract/test_agent_conversation_api.py`
- [ ] T023 [P] [US1] Add unit cases for pure greeting, thanks, goodbye, capability help, and mixed greeting-plus-task boundaries in `backend/tests/unit/test_conversation_fast_route.py`
- [ ] T024 [P] [US1] Add integration tests proving greetings persist before reply and create no tool/task/write records in `backend/tests/integration/test_conversation_greeting.py`
- [ ] T025 [P] [US1] Add component tests for optimistic user messages, assistant text, empty/loading/error states, and keyboard submission in `frontend/tests/component/agent-conversation.spec.ts`

### Implementation for User Story 1

- [ ] T026 [P] [US1] Implement deterministic pure-conversation and current-capability-help responses in `backend/app/modules/agent/conversation_router.py`
- [ ] T027 [US1] Implement conversation CRUD, message acceptance, pagination, and CSRF/ownership enforcement in `backend/app/modules/agent/router.py`
- [ ] T028 [US1] Add fast-route Turn execution and persisted assistant-message creation in `backend/app/workers/tasks/agent.py`
- [ ] T029 [P] [US1] Implement typed conversation and message API client with client-generated idempotency IDs in `frontend/src/api/agentConversations.ts`
- [ ] T030 [P] [US1] Implement persisted conversation/message state, optimistic reconciliation, and pagination in `frontend/src/stores/agentConversations.ts`
- [ ] T031 [US1] Replace the single-task composer with a mobile-accessible conversation shell while preserving existing Agent result components in `frontend/src/modules/agent/AgentPage.vue`

**Checkpoint**: The Agent is demonstrably conversational for greetings and truthful capability help, while the existing task API remains unchanged.

---

## Phase 4: User Story 2 — Recognize Tasks in Conversation (Priority: P1)

**Goal**: Natural, mixed, and multi-turn messages become validated existing Agent tasks or one minimal clarification; internal writes still require structured confirmation.

**Independent Test**: Send “嗨，帮我找最近十篇文章” and then “把刚才那些提取标签并保存”; verify exact scope inheritance, analysis, waiting confirmation, zero pre-approval writes, and approved persistence.

### Tests for User Story 2

- [ ] T032 [P] [US2] Add structured route contract tests for every route kind, operation type, scope source, candidate limit, and invalid extra field in `backend/tests/contract/test_conversation_route_contract.py`
- [ ] T033 [P] [US2] Add at least 30 Chinese/English/paraphrased task variants plus mixed greeting/task cases in `backend/tests/unit/test_conversation_routing.py`
- [ ] T034 [P] [US2] Add policy tests for candidate membership, permission, availability, read/write mismatch, confidence threshold, and minimal clarification in `backend/tests/unit/test_capability_selector.py`
- [ ] T035 [P] [US2] Add multi-turn scope, stale object, repeated-success skip, and clarification-resume tests in `backend/tests/integration/test_conversation_context.py`
- [ ] T036 [P] [US2] Add security tests proving quoted “确认” text and model-proposed approval cannot authorize writes in `backend/tests/security/test_conversation_confirmation.py`
- [ ] T037 [P] [US2] Add E2E coverage for conversational query → follow-up analysis → confirmation preview → approve/reject in `frontend/tests/e2e/agent-conversation-task.spec.ts`

### Implementation for User Story 2

- [ ] T038 [US2] Add the versioned `conversation_route` structured LLM scenario and prompt configuration in `backend/app/services/llm/schemas.py` and `backend/app/services/llm/gateway.py`
- [ ] T039 [US2] Implement capability candidate reduction from safe names, responsibilities, operation types, scopes, permissions, and availability in `backend/app/modules/agent/capability_selector.py`
- [ ] T040 [US2] Implement structured LLM routing, schema validation, confidence fallback, and one-question clarification in `backend/app/modules/agent/conversation_router.py`
- [ ] T041 [US2] Persist routing decisions without hidden reasoning and bridge accepted task routes to existing AgentTask/Job execution in `backend/app/modules/agent/conversation_service.py`
- [ ] T042 [US2] Extend conversation context inheritance with object IDs, versions, completed/failed items, refresh notices, and pending confirmations in `backend/app/modules/agent/service.py`
- [ ] T043 [US2] Resume a waiting-clarification Turn from the next user message without expanding its original scope in `backend/app/workers/tasks/agent.py`
- [ ] T044 [US2] Render clarification prompts, linked task results, capability gaps, and existing ConfirmationCard actions inside the conversation timeline in `frontend/src/modules/agent/AgentPage.vue`

**Checkpoint**: Existing internal Agent abilities can be reached through ordinary conversation and multi-turn references, with all existing confirmation protections intact.

---

## Phase 5: User Story 3 — Select Authorized MCP Tools (Priority: P2)

**Goal**: The router can discover, shortlist, authorize, invoke, and truthfully report preconfigured MCP tools without exposing secrets or obeying tool-output instructions.

**Independent Test**: An authorized read-only MCP stub completes a natural-language request; disconnecting it yields a truthful retryable failure; malicious output cannot trigger another tool or approval.

### Tests for User Story 3

- [ ] T045 [P] [US3] Add an official-SDK-compatible Streamable HTTP MCP stub with read, write, invalid-schema, oversized, timeout, and malicious-output tools in `backend/tests/fixtures/mcp_server.py`
- [ ] T046 [P] [US3] Add discovery/cache/schema-normalization contract tests against the MCP stub in `backend/tests/contract/test_mcp_discovery.py`
- [ ] T047 [P] [US3] Add safe manifest v2 contract tests proving only approved fields and schemas are exposed in `backend/tests/contract/test_agent_capabilities.py`
- [ ] T048 [P] [US3] Add integration tests for natural-language MCP selection, parameter generation, actual result return, and audit linkage in `backend/tests/integration/test_agent_mcp_execution.py`
- [ ] T049 [P] [US3] Add integration tests for MCP write preview, grant/version recheck, approve, reject, and idempotent external effect in `backend/tests/integration/test_agent_mcp_write.py`
- [ ] T050 [P] [US3] Add security tests for arbitrary URL/redirect SSRF, disabled tools, revoked grants, token passthrough, cross-user capability leakage, and credential redaction in `backend/tests/security/test_mcp_authorization.py`
- [ ] T051 [P] [US3] Add prompt-injection tests proving MCP output and server instructions cannot alter route, scope, grant, confirmation, or follow-up invocation in `backend/tests/security/test_mcp_prompt_injection.py`
- [ ] T052 [P] [US3] Add reliability tests for offline, timeout, invalid JSON, unknown media, oversized result, bounded retry, and successful-part preservation in `backend/tests/reliability/test_mcp_failures.py`

### Implementation for User Story 3

- [ ] T053 [US3] Implement MCP connection bootstrap and safe connection metadata synchronization from config keys in `backend/app/services/mcp/config.py` and `backend/app/modules/agent/conversation_service.py`
- [ ] T054 [US3] Implement `server/discover`/legacy initialization fallback, tool listing, TTL/ETag catalog caching, and health status updates in `backend/app/services/mcp/provider.py`
- [ ] T055 [US3] Normalize MCP tool schemas and register namespaced tools as `mcp.<connection>.<tool>` without server instructions in `backend/app/services/mcp/gateway.py`
- [ ] T056 [US3] Implement tool-level McpToolGrant evaluation and immediate revocation checks in `backend/app/modules/agent/registry.py`
- [ ] T057 [US3] Implement selected-tool argument generation, JSON Schema validation, minimal-data projection, and operation classification in `backend/app/modules/agent/capability_selector.py`
- [ ] T058 [US3] Implement read-only MCP invocation with idempotency key, result validation, size/media limits, stable errors, trace propagation, and ExecutionRecord writes in `backend/app/modules/agent/conversation_service.py`
- [ ] T059 [US3] Adapt eligible MCP write tools into PendingWrite previews and block tools whose impact cannot be previewed in `backend/app/modules/agent/service.py`
- [ ] T060 [US3] Expose the owned safe capability manifest and connection health summaries without configuration secrets in `backend/app/modules/agent/router.py`
- [ ] T061 [US3] Add operator MCP connection bootstrap, health-check, and safe catalog diagnostics without secret output in `backend/app/cli/mcp.py` and `backend/app/cli/main.py`

**Checkpoint**: Authorized MCP reads work end-to-end; eligible writes use the same confirmation boundary; unavailable or unsafe tools are never simulated.

---

## Phase 6: User Story 4 — Understand the Execution Inside Chat (Priority: P2)

**Goal**: Messages, task stages, tools, confirmations, results, and failures appear in one ordered, reconnect-safe conversation timeline.

**Independent Test**: Run a conversation containing internal query, MCP query, clarification, and pending write; reload and reconnect SSE, then verify every UI item is attached to the correct user message and Turn.

### Tests for User Story 4

- [ ] T062 [P] [US4] Add SSE contract tests for conversation message/turn events, safe field limits, replay, and active-Turn snapshots in `backend/tests/contract/test_conversation_events.py`
- [ ] T063 [P] [US4] Add integration tests for ordering and linkage across simultaneous Turns, assistant messages, AgentTasks, and confirmations in `backend/tests/integration/test_conversation_timeline.py`
- [ ] T064 [P] [US4] Add component tests for message roles, stage labels, result status distinctions, clarification, tool activity, and confirmation ownership in `frontend/tests/component/conversation-timeline.spec.ts`
- [ ] T065 [P] [US4] Add SSE reconnect/snapshot and page-reload E2E coverage in `frontend/tests/e2e/agent-conversation-reconnect.spec.ts`

### Implementation for User Story 4

- [ ] T066 [US4] Publish `conversation.message_created` and `conversation.turn_updated` transactionally with safe payloads in `backend/app/modules/agent/status.py`
- [ ] T067 [US4] Include active Turns and latest safe message cursor in job SSE snapshots and Last-Event-ID replay in `backend/app/modules/jobs/sse.py`
- [ ] T068 [P] [US4] Implement reusable message bubble, result status, and accessible timestamp rendering in `frontend/src/components/agent/ConversationMessage.vue`
- [ ] T069 [P] [US4] Implement clarification and capability/tool activity cards without infrastructure vocabulary in `frontend/src/components/agent/ClarificationCard.vue` and `frontend/src/components/agent/ToolActivityCard.vue`
- [ ] T070 [US4] Implement ordered Turn/message/task/confirmation composition and stable keyed updates in `frontend/src/components/agent/ConversationTimeline.vue`
- [ ] T071 [US4] Route conversation SSE events and snapshots into the conversation store with deduplication in `frontend/src/stores/jobs.ts` and `frontend/src/stores/agentConversations.ts`
- [ ] T072 [US4] Integrate timeline, composer, pagination, live status, and existing confirmation actions in `frontend/src/modules/agent/AgentPage.vue`

**Checkpoint**: The conversation UI survives refresh/reconnect and clearly distinguishes queried, generated, pending, saved, failed, and unprocessed outcomes.

---

## Phase 7: User Story 5 — Recover from Failures and Stalls (Priority: P3)

**Goal**: Every worker error becomes a durable user-visible state; stalled work is detected and safely retryable without duplicate effects.

**Independent Test**: Kill the worker before terminal persistence, wait for watchdog, reload, and retry; verify stalled status appears and no successful internal or external step runs twice.

### Tests for User Story 5

- [ ] T073 [P] [US5] Add worker top-level exception tests for failures before run creation, during routing, during tool selection, and after partial result persistence in `backend/tests/reliability/test_agent_turn_finalizer.py`
- [ ] T074 [P] [US5] Add watchdog tests for heartbeat threshold, terminal exclusion, race locking, linked Task/Job repair, and user-visible stalled errors in `backend/tests/reliability/test_agent_turn_watchdog.py`
- [ ] T075 [P] [US5] Add retry tests for duplicate clicks, repeated delivery, completed-step skipping, revoked capability, and external idempotency keys in `backend/tests/integration/test_agent_turn_retry.py`
- [ ] T076 [P] [US5] Add restart recovery tests preserving conversation, scope, pending confirmation, successful parts, and messages in `backend/tests/integration/test_conversation_restart.py`
- [ ] T077 [P] [US5] Add component tests for timeout/stalled copy, retry disabled states, and retry reconciliation in `frontend/tests/component/agent-turn-retry.spec.ts`

### Implementation for User Story 5

- [ ] T078 [US5] Wrap Turn execution in a top-level finalizer that persists failed/partial states in an independent transaction in `backend/app/workers/tasks/agent.py`
- [ ] T079 [US5] Update heartbeats at bounded stage transitions and implement locked stalled-Turn repair in `backend/app/modules/agent/watchdog.py`
- [ ] T080 [US5] Schedule the watchdog on the existing beat process without adding queues in `backend/app/workers/beat_schedule.py` and `backend/app/workers/tasks/maintenance.py`
- [ ] T081 [US5] Implement owned, idempotent retry eligibility and retry-of linkage in `backend/app/modules/agent/conversation_service.py`
- [ ] T082 [US5] Expose Turn detail and retry endpoints with CSRF, conflict, and retryability semantics in `backend/app/modules/agent/router.py`
- [ ] T083 [US5] Add stalled/failure guidance and retry controls while preserving the original timeline in `frontend/src/modules/agent/AgentPage.vue` and `frontend/src/stores/agentConversations.ts`

**Checkpoint**: No injected worker failure leaves a Turn, AgentTask, or Job indefinitely accepted/routing/executing; retry does not duplicate effects.

---

## Phase 8: Polish and Cross-Cutting Validation

**Purpose**: Verify security, performance, deployment, documentation, and full regression coverage across all stories.

- [ ] T084 [P] Add up-to-100-tool routing latency and manifest-size performance coverage in `backend/tests/performance/test_conversation_routing_latency.py`
- [ ] T085 [P] Add conversation keyboard navigation, focus, screen-reader labels, mobile layout, and contrast checks in `frontend/tests/e2e/agent-conversation-accessibility.spec.ts`
- [ ] T086 [P] Add full-record secret/private-content scanning across messages, routes, status events, logs, and execution records in `backend/tests/security/test_conversation_redaction.py`
- [ ] T087 Verify database indexes and bounded message/catalog queries with query-plan assertions in `backend/tests/performance/test_conversation_queries.py`
- [ ] T088 Add MCP secret rotation, grant revocation, health diagnosis, watchdog, and safe log procedures in `docs/operations.md`
- [ ] T089 Add conversation and MCP metadata backup/restore expectations while excluding secret material in `docs/backup-restore.md`
- [ ] T090 Add Compose readiness checks for MCP config parsing, worker health, migrations, and no-MCP degraded startup in `deploy/scripts/smoke.sh`
- [ ] T091 Execute every scenario in `specs/008-conversational-agent-mcp/quickstart.md` and record command/evidence updates in that file
- [ ] T092 Run backend lint/type/unit/contract/integration/security/reliability/performance suites plus frontend lint/type/component/E2E/build and record the final acceptance result in `specs/008-conversational-agent-mcp/checklists/requirements.md`

---

## Dependencies and Execution Order

### Phase dependencies

- Phase 1 integrates the required self-service Agent baseline.
- Phase 2 depends on Phase 1 and blocks every user story.
- US1 depends only on Phase 2 and is the conversational MVP.
- US2 depends on US1's conversation shell and Phase 2 route foundation.
- US3 depends on US2's structured routing and capability selector; its MCP gateway foundation is built in Phase 2.
- US4 depends on US1 and can proceed alongside the later half of US2/US3 once event payloads stabilize.
- US5 depends on durable Turns from Phase 2 and can proceed alongside US3/US4 after state transitions stabilize.
- Phase 8 follows all stories selected for release.

### User story completion order

```text
Setup → Foundation → US1 → US2 → US3
                      ├──────→ US4
                      └──────→ US5
US2 + US3 + US4 + US5 → Polish
```

### Parallel opportunities

- T003–T005 can run together after T001.
- T007–T010 are independent tests and can run together before T011–T021.
- Within every story, test tasks marked `[P]` can be written concurrently before implementation.
- After Phase 2, backend US1 fast routing and frontend API/store work can proceed concurrently.
- US4 components T068–T069 can run concurrently; US5 reliability tests T073–T077 can run concurrently.
- Polish tests T084–T086 can run concurrently.

## Parallel Examples

### User Story 1

```text
T022 REST conversation contracts
T023 fast-route unit matrix
T024 durable greeting integration
T025 conversation component tests
```

### User Story 3

```text
T045 MCP protocol stub
T046 discovery contracts
T047 safe manifest contracts
T048 read execution integration
T049 write confirmation integration
T050 authorization security
T051 prompt-injection security
T052 dependency failure injection
```

### User Story 5

```text
T073 finalizer failures
T074 watchdog races
T075 retry idempotency
T076 restart recovery
T077 frontend retry states
```

## Implementation Strategy

### MVP first

1. Complete T001–T021.
2. Complete T022–T031 for normal conversation.
3. Stop and demonstrate `hi` and truthful capability help with no task/tool side effects.
4. Continue T032–T044 to make existing Agent tasks conversational.

### Incremental delivery

1. Baseline + foundation: durable conversation primitives, no UX regression.
2. US1: normal conversation.
3. US2: existing internal tasks recognized from conversation.
4. US3: authorized MCP reads, then eligible confirmed writes.
5. US4: complete live timeline and reconnect behavior.
6. US5: failure finalization, watchdog, and idempotent retry.
7. Polish: security, performance, operations, backup, Compose, and full acceptance.

## Task Summary

- Total: 92 tasks
- Setup and foundation: 21 tasks
- US1: 10 tasks
- US2: 13 tasks
- US3: 17 tasks
- US4: 11 tasks
- US5: 11 tasks
- Polish: 9 tasks
- All story phases place tests before implementation and every task includes an exact file or directory path.
