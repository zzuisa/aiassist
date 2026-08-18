# Tasks: 对话式协作 Agent 调度

**Input**: Design documents from `specs/011-collaborative-agent-orchestration/`

## Phase 1: Setup

- [x] T001 Register the `agent_task_plan` AI configuration module in `backend/app/modules/ai_config/catalog.py`
- [x] T002 [P] Add strict planning and public plan schemas in `backend/app/modules/agent/planning_schemas.py`
- [x] T003 [P] Add frontend plan API types and client methods in `frontend/src/api/agentPlans.ts`

## Phase 2: Foundational

- [x] T004 Add execution plan, step, dependency, artifact and attempt models in `backend/app/models/agent.py`
- [x] T005 Add the collaborative plan database migration in `backend/alembic/versions/`
- [x] T006 [P] Add contract tests for planning and event JSON schemas in `backend/tests/contract/test_agent_plan_contract.py`
- [x] T007 [P] Add unit tests for DAG, scope and tool policy validation in `backend/tests/unit/test_agent_planning.py`
- [x] T008 Implement plan proposal, validation, persistence and public serialization in `backend/app/modules/agent/planning_service.py`
- [x] T009 Extend plan status event publication and SSE snapshots in `backend/app/modules/agent/status.py` and `backend/app/modules/jobs/sse.py`

## Phase 3: User Story 1 - 实时查看任务计划与执行

**Goal**: Every task turn shows a durable live plan before business execution.

**Independent Test**: Submit a two-step read request and observe a persisted plan and live step transitions without refreshing.

- [x] T010 [P] [US1] Add plan REST contract tests in `backend/tests/contract/test_agent_plan_api.py`
- [x] T011 [P] [US1] Add SSE replay and snapshot integration tests in `backend/tests/integration/test_agent_plan_events.py`
- [x] T012 [US1] Add owned plan query endpoints in `backend/app/modules/agent/router.py`
- [x] T013 [P] [US1] Add plan state handling to `frontend/src/stores/agentConversations.ts`
- [x] T014 [P] [US1] Implement accessible live step rendering in `frontend/src/components/agent/AgentPlanStep.vue`
- [x] T015 [US1] Implement the inline plan card in `frontend/src/components/agent/AgentPlanCard.vue`
- [x] T016 [US1] Attach plans to their conversation turns in `frontend/src/components/agent/ConversationTimeline.vue` and `frontend/src/components/agent/ConversationPanel.vue`

## Phase 4: User Story 2 - 任务拆解与异步协作

**Goal**: Plan composite tasks and run dependency-ready steps concurrently through durable workers.

**Independent Test**: Execute query → parallel analysis → aggregation in one turn and verify dependency artifact scope.

- [x] T017 [P] [US2] Add planner Prompt and policy integration tests in `backend/tests/integration/test_agent_collaborative_planning.py`
- [x] T018 [P] [US2] Add scheduler concurrency, dependency and partial-failure tests in `backend/tests/integration/test_agent_plan_scheduler.py`
- [x] T019 [US2] Implement the versioned planning LLM call and safe tool/Agent assignment in `backend/app/modules/agent/planning_service.py`
- [x] T020 [US2] Implement dependency claiming, terminal propagation and finalization in `backend/app/modules/agent/scheduler.py`
- [x] T021 [US2] Implement internal query, analysis, capability-gap and MCP step adapters in `backend/app/modules/agent/step_executor.py`
- [x] T022 [US2] Add plan coordination and step Celery tasks in `backend/app/workers/tasks/agent.py`
- [x] T023 [US2] Change conversation task turns to persist and dispatch a plan before execution in `backend/app/modules/agent/conversation_service.py`
- [x] T024 [US2] Adapt legacy `/agent/tasks` creation to the plan scheduler in `backend/app/modules/agent/router.py`

## Phase 5: User Story 3 - 完成后自动折叠并可追溯展开

**Goal**: Active plans stay visible and terminal plans collapse once while remaining expandable.

**Independent Test**: Finish a three-step plan, observe automatic collapse, expand it, and ensure later events preserve the manual state.

- [x] T025 [P] [US3] Add component tests for live status and one-time terminal collapse in `frontend/tests/component/agent-plan-card.spec.ts`
- [x] T026 [US3] Implement terminal transition and manual expansion ownership in `frontend/src/components/agent/AgentPlanCard.vue`
- [x] T027 [US3] Restore recent conversation plans and preserve their terminal traces in `frontend/src/stores/agentConversations.ts`

## Phase 6: User Story 4 - 安全确认、失败恢复与重试

**Goal**: Write barriers and failed-chain retries reuse valid work without duplicate effects.

**Independent Test**: Fail a middle step, retry only its affected chain, and approve a write exactly once.

- [x] T028 [P] [US4] Add write barrier and failed-chain retry integration tests in `backend/tests/integration/test_agent_plan_retry_confirmation.py`
- [x] T029 [P] [US4] Add plan event leakage security tests in `backend/tests/security/test_agent_plan_event_leakage.py`
- [x] T030 [US4] Connect PendingWrite decisions back to plan steps and resume coordination in `backend/app/modules/agent/service.py`
- [x] T031 [US4] Implement failed-chain retry and plan watchdog recovery in `backend/app/modules/agent/scheduler.py` and `backend/app/modules/agent/watchdog.py`
- [x] T032 [US4] Add plan retry API and frontend retry action in `backend/app/modules/agent/router.py` and `frontend/src/components/agent/AgentPlanCard.vue`

## Final Phase: Polish & Cross-Cutting Concerns

- [x] T033 Run backend focused and regression tests and fix failures in `backend/tests/`
- [x] T034 Run frontend typecheck, lint, component tests and production build; document live-deployment E2E deferral in `quickstart.md`
- [x] T035 Update the Agent user guide with planning, collaboration, confirmation and retry behavior in `docs/agent-user-guide.md`
- [x] T036 Validate the end-to-end scenarios in `specs/011-collaborative-agent-orchestration/quickstart.md`

## Dependencies

```text
Setup -> Foundational -> US1 -> US2 -> US3 -> US4 -> Polish
                         \------ UI work may proceed alongside scheduler adapters ------/
```

- US1 requires the persistent plan and event contract.
- US2 requires plan persistence and is the core execution path.
- US3 requires US1 plan events and can be completed independently of write retry.
- US4 requires US2 scheduling and the existing PendingWrite boundary.

## Parallel Opportunities

- T002 and T003 can proceed independently after T001.
- T006 and T007 can be written while T004/T005 are prepared.
- T013 and T014 can proceed after the public contract is stable.
- T017 and T018 cover separate planner and scheduler concerns.
- T025, T028 and T029 affect independent test surfaces.

## Implementation Strategy

1. Establish plan schemas, persistence and safe events.
2. Deliver the live read-only plan UI as the first independently demonstrable increment.
3. Replace synchronous conversation execution with the durable scheduler and supported step adapters.
4. Add terminal folding, write barriers and failed-chain retry.
5. Run focused suites first, then broader backend/frontend validation.

**Task count**: 36. **Suggested MVP**: T001–T024, which provides visible durable planning and asynchronous read/analysis collaboration.
