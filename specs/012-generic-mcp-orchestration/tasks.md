# Tasks: LangGraph Generic MCP Orchestration

**Input**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`

## Phase 1: Setup

- [X] T001 Add locked LangGraph runtime dependencies in `backend/pyproject.toml`, `backend/requirements.lock.txt`, and `backend/requirements-dev.lock.txt`.
- [X] T002 Add Graph Runtime module boundaries under `backend/app/modules/agent/` without exposing MCP clients to the planning model.

## Phase 2: Foundational

- [X] T003 [P] Add unit coverage for Graph state, fixed graph topology, and `thread_id` configuration in `backend/tests/unit/test_agent_graph_runtime.py`.
- [X] T004 Add the LangGraph runtime and fixed safe graph in `backend/app/modules/agent/graph_runtime.py`.
- [X] T005 Replace the plan Celery coordinator with one Graph invoke/resume task in `backend/app/workers/tasks/agent.py`.

## Phase 3: User Story 1 - Execute bounded MCP plans (Priority: P1)

- [X] T006 [US1] Route accepted plans through Graph Runtime while preserving ToolRegistry, ownership, confirmation, idempotency, and verification gates in `backend/app/modules/agent/graph_runtime.py`.
- [X] T007 [US1] Persist Graph run/thread references and runtime state in `backend/app/models/agent.py` and the matching Alembic migration.
- [X] T008 [US1] Update retry, cancel, confirmation resume, and stalled-plan repair paths to issue Graph resume commands in `backend/app/modules/agent/router.py`, `backend/app/modules/agent/scheduler.py`, and `backend/app/modules/agent/status.py`.
- [X] T009 [US1] Add integration coverage for worker redelivery, confirmation resume, and no duplicate operator effects in `backend/tests/integration/test_agent_graph_runtime.py`.

## Phase 4: Polish

- [X] T010 [P] Update Graph deployment/checkpointer setup and operator runbook in `specs/012-generic-mcp-orchestration/quickstart.md` and `docs/operations.md`.
- [X] T011 Run focused agent tests, contract validation, and lint; record migration risks in `specs/012-generic-mcp-orchestration/quickstart.md`.

## Phase 5: Foundational completion - capability truth and persisted reports

**Purpose**: Close the gap between the completed LangGraph runtime slice and the full 012 specification.

- [X] T012 [P] Add capability-snapshot, safe-name mapping, and per-user MCP authorization tests in `backend/tests/unit/test_agent_capability_snapshot.py` and `backend/tests/security/test_mcp_authorization.py`.
- [X] T013 [P] Add report reconciliation and API schema coverage in `backend/tests/unit/test_agent_report_service.py` and the agent contract suite.
- [X] T014 Add capability snapshot and task report entities plus plan phase/counter fields in `backend/app/models/agent.py` and `backend/alembic/versions/0025_complete_mcp_orchestration.py`.
- [X] T015 Implement immutable per-task capability snapshots and 64-character provider-name mappings in `backend/app/modules/agent/capability_snapshot_service.py` and `backend/app/modules/agent/registry.py`.
- [X] T016 Implement deterministic `task-report.v1` reconciliation, regeneration, and ownership-safe report APIs in `backend/app/modules/agent/report_service.py`, `backend/app/modules/agent/router.py`, and `backend/app/modules/agent/schemas.py`.

## Phase 6: User Story 1 - Execute semantic read-only MCP plans (Priority: P1)

**Goal**: A request such as “查询一篇关于情感的博客” selects the authorized blog search MCP, preserves the query and limit, executes it, and returns matching articles.

**Independent Test**: With an authorized blog MCP catalog, submit the reference query and verify the plan uses the safe search capability with `query=情感`, `limit=1`, and returns only the matching article.

- [X] T017 [P] [US1] Add semantic routing and MCP artifact normalization coverage in `backend/tests/unit/test_agent_emotion_tag_workflow.py` and `backend/tests/integration/test_agent_mcp_execution.py`.
- [X] T018 [P] [US1] Add production-safe first-party blog MCP authorization coverage and the safe `mcp-diagnose` command.
- [X] T019 [US1] Make candidate selection schema-aware and preserve semantic query/cardinality arguments in `backend/app/modules/agent/capability_selector.py`, `backend/app/modules/agent/conversation_router.py`, and `backend/app/modules/agent/conversation_service.py`.
- [X] T020 [US1] Normalize MCP structured results, validate output schemas, and propagate safe object scope through artifacts in `backend/app/modules/agent/step_executor.py` and `backend/app/services/mcp/gateway.py`.
- [X] T021 [US1] Provision reviewed first-party blog MCP policies and explicit user-bound grants through `deploy/scripts/deploy.sh`, `backend/app/modules/agent/conversation_service.py`, and `deploy/secrets/mcp-connections.example.json` without committing credentials.

## Phase 7: User Story 2 - Orchestrate the emotion-blog tag workflow safely (Priority: P1)

**Goal**: Search exactly eight emotion-related posts, identify posts without tags, read only those bodies, generate tag proposals with the LLM, preview, confirm, apply, verify, and reconcile the outcome without overwriting existing tags.

**Independent Test**: Submit “帮我查询8篇关于情感的博客，并且查看是否都有标签，如果没有则通过llm优化给每篇生成标签”; verify eight bounded search matches, already-tagged posts are preserved, missing-tag posts receive proposals, no write occurs before confirmation, conflicts remain unchanged, and only read-back verified updates count as success.

- [X] T022 [P] [US2] Add exact eight-item emotion-search and five-stage artifact-flow coverage in `backend/tests/unit/test_agent_emotion_tag_workflow.py` and the existing agent integration suite.
- [X] T023 [P] [US2] Cover idempotency, existing-tag preservation, version conflicts, no-write-before-approval, and prompt injection in the agent security/integration suites.
- [X] T024 [US2] Implement owned tag read-back verification through the reviewed internal registry tool and retain Blog MCP discovery contract coverage.
- [X] T025 [US2] Implement typed select/filter/analyze/mutate/verify dependency artifact bindings and bounded map execution in `backend/app/modules/agent/planning_service.py` and `backend/app/modules/agent/step_executor.py`.
- [X] T026 [US2] Run the fixed phase graph with confirmation interrupt/resume flow in `backend/app/modules/agent/graph_runtime.py` and `backend/app/workers/tasks/agent.py`.
- [X] T027 [US2] Persist mutation and verification artifacts and reconcile them into `task-report.v1`.

## Phase 8: User Story 3 - See meaningful live orchestration progress (Priority: P2)

**Goal**: The initiating turn immediately shows routing, planning, active MCP/tool work, confirmation waits, verification, reporting, and completion through replayable SSE snapshots.

**Independent Test**: Delay routing and two operators independently and verify every committed phase becomes visible within two seconds without REST polling or replaying old history.

- [X] T028 [P] [US3] Validate transaction timing, SSE recovery, and frontend store events through the existing agent SSE/plan-event/component suites.
- [X] T029 [US3] Split routing/planning execution into short committed phases and publish bounded conversation/plan events in `backend/app/workers/tasks/agent.py`, `backend/app/modules/agent/conversation_service.py`, and `backend/app/modules/agent/status.py`.
- [X] T030 [US3] Extend the public plan projection with phase/count/action/report fields in `backend/app/modules/agent/planning_schemas.py` and `backend/app/modules/agent/planning_service.py`.
- [X] T031 [US3] Make the Agent conversation store SSE-first with reconnect snapshot fallback and remove active-turn 700ms polling in `frontend/src/stores/agentConversations.ts` and `frontend/src/stores/jobs.ts`.
- [X] T032 [US3] Add a compact accessible live orchestration strip with reduced-motion support in `frontend/src/components/agent/AgentProgressStrip.vue`, `frontend/src/components/agent/AgentPlanCard.vue`, and `frontend/src/modules/agent/AgentPage.vue`.

## Phase 9: User Story 4 - Receive a reconciled Markdown report (Priority: P2)

**Goal**: Every terminal task exposes a compact summary and an on-demand valid Markdown report based only on persisted terminal facts.

**Independent Test**: Complete a read-only and a partially failed mutation task; verify report totals match persisted outcomes and regeneration performs no MCP or business mutation calls.

- [X] T033 [P] [US4] Add frontend report-card coverage in `frontend/tests/component/agent-task-report.spec.ts` and complete the reference workflow against production APIs.
- [X] T034 [US4] Add report API client types and safe Markdown report rendering in `frontend/src/api/agentReports.ts` and `frontend/src/components/agent/TaskReportCard.vue`.
- [X] T035 [US4] Link the latest report into the initiating conversation turn and load it on demand in `frontend/src/modules/agent/AgentPage.vue` and `frontend/src/stores/agentConversations.ts`.

## Phase 10: Cross-cutting validation and production rollout

- [X] T036 [P] Add MCP orchestration operator runbook and secure first-party connection bootstrap instructions in `docs/operations.md` and `specs/012-generic-mcp-orchestration/quickstart.md`.
- [X] T037 Run backend unit/contract/integration/security suites plus Ruff, format, Mypy, frontend lint/typecheck/tests/build, and the production E2E reference scenario.
- [X] T038 Configure the production first-party blog MCP secret/grants, deploy from `master`, verify migrations and service health, and archive the incident fix in `docs/fix-reports/` plus an internal AI Assist article.

## Dependencies

`T001 -> T002 -> T003/T004 -> T005 -> T006/T007 -> T008 -> T009 -> T010/T011`

`T012/T013 -> T014 -> T015/T016 -> T017/T018 -> T019 -> T020 -> T021 -> T022/T023 -> T024 -> T025 -> T026 -> T027 -> T028 -> T029 -> T030 -> T031/T032 -> T033 -> T034 -> T035 -> T036/T037 -> T038`

## MVP

T001-T011 provide the demonstrable LangGraph runtime slice already delivered. T012-T021 are the corrected read-only MCP orchestration MVP. T022-T038 complete the eight-emotion-blog tag workflow, live-progress, report, and production requirements.
