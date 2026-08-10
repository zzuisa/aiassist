# Tasks: 博客 Agent 内容管理

**Input**: Design documents from `specs/006-agent-content-management/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Tests are REQUIRED. Unit, contract, integration, security, reliability, component and E2E tests appear before the implementation tasks they validate.

**Organization**: Tasks are grouped by user story so each increment can be tested and delivered independently after the shared foundation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and has no unmet dependency on another task in the same group.
- **[Story]**: User story mapping from spec.md.
- Every task includes an exact repository-relative file path.

## Phase 1: Setup (Contracts and Shared Test Fixtures)

**Purpose**: Make the approved contracts executable before domain implementation.

- [ ] T001 Add contract loaders and positive/negative samples for `blog-agent-config.v1` and `blog-orchestration-snapshot.v1` in `backend/tests/contract/test_blog_agent_contracts.py`
- [ ] T002 [P] Add OpenAPI/AsyncAPI drift assertions for every Agent route and identifier-only preview message in `backend/tests/contract/test_blog_agent_contracts.py`
- [ ] T003 [P] Add reusable Agent config, manifest, capability and snapshot factories without real secrets in `backend/tests/factories.py`
- [ ] T004 [P] Define frontend topology, version, activation, preview and snapshot contract types matching `contracts/openapi.yaml` in `frontend/src/api/blogAgents.ts`
- [ ] T005 Register the two JSON schemas as runtime test resources and validate their Draft 2020-12 metaschemas in `backend/tests/contract/test_blog_agent_contracts.py`

---

## Phase 2: Foundational (Blocking Domain Infrastructure)

**Purpose**: Establish immutable versions, activation, snapshots, previews, schema validation and manifest invariants used by every story.

**⚠️ CRITICAL**: No user story implementation starts until this phase passes migration, model, contract and ownership foundations.

### Tests first

- [ ] T006 [P] Add migration upgrade/downgrade assertions that preserve existing BlogSkill, PostAIRun and PostAICandidate rows in `backend/tests/integration/test_blog_agent_management.py`
- [ ] T007 [P] Add model constraint and immutability tests for AgentVersion, AgentActivation, OrchestrationSnapshot and AgentPreview in `backend/tests/unit/test_blog_models.py`
- [ ] T008 [P] Add unit tests for allowed placeholders, size limits, parameter bounds, secret-pattern rejection and locked-field rejection in `backend/tests/unit/test_blog_prompt_assembly.py`
- [ ] T009 [P] Add manifest tests for stable keys, complete edges, acyclic order and mandatory validator/candidate paths in `backend/tests/unit/test_blog_agent_manifest.py`
- [ ] T010 [P] Add cross-user read/write matrix tests for version, activation, preview and snapshot resources in `backend/tests/security/test_blog_agent_security.py`

### Implementation

- [ ] T011 Create migration tables, constraints and indexes from data-model.md in `backend/alembic/versions/0019_blog_agent_content_management.py`
- [ ] T012 Add BlogAgentVersion, BlogAgentActivation, BlogOrchestrationSnapshot and BlogAgentPreview SQLAlchemy models in `backend/app/models/blog.py`
- [ ] T013 [P] Add strict Pydantic DTOs and runtime schema adapters for Agent config, topology, activation, preview and snapshot in `backend/app/modules/posts/agent_schemas.py`
- [ ] T014 [P] Implement versioned system manifest definitions and graph invariant validation in `backend/app/modules/posts/agent_manifest.py`
- [ ] T015 Implement canonical hashing, placeholder allowlist, secret detection, locked-field enforcement and compatibility validation in `backend/app/modules/posts/agent_service.py`
- [ ] T016 Add safe structured logging fields/denylist coverage for agent_config, prompt sections and capability descriptors in `backend/app/core/observability.py`
- [ ] T017 Create the `/blog/agents` router shell with authenticated ownership and CSRF dependency boundaries in `backend/app/modules/posts/agent_router.py`
- [ ] T018 Register the Agent router without changing existing route order or public blog behavior in `backend/app/main.py`
- [ ] T019 Run the Phase 2 migration/model/contract/security tests and record any contract corrections in `specs/006-agent-content-management/contracts/openapi.yaml`

**Checkpoint**: The database and typed domain foundation exist, invalid/private data is rejected, and the system manifest is safe to expose.

---

## Phase 3: User Story 1 - 看懂完整执行结构 (Priority: P1) 🎯 MVP

**Goal**: Show the real blog enhancement chain by stage, condition and dependency, with a semantic mobile/list equivalent.

**Independent Test**: Open `/blog/agents` and identify input/Skill match, orchestrator, Editor/Logic/Data/Scene/Illustration, capabilities, quality validation and candidate persistence in their true order, including disabled/unavailable nodes.

### Tests for User Story 1 (write first)

- [ ] T020 [P] [US1] Add topology endpoint contract tests for node kinds, ordered stages, edges, execution modes and safe statuses in `backend/tests/contract/test_blog_agent_contracts.py`
- [ ] T021 [P] [US1] Add integration tests that merge manifest defaults with an owned activation while retaining unavailable nodes in `backend/tests/integration/test_blog_agent_management.py`
- [ ] T022 [P] [US1] Add component tests for stage rendering, conditional badges, filters, details and list fallback in `frontend/tests/component/blog-agents.spec.ts`
- [ ] T023 [P] [US1] Add 360px, keyboard and accessible-name E2E coverage for the complete execution structure in `frontend/tests/e2e/blog-agent-management.spec.ts`

### Implementation for User Story 1

- [ ] T024 [US1] Implement topology/detail serialization from manifest plus owned activation state in `backend/app/modules/posts/agent_service.py`
- [ ] T025 [US1] Implement `GET /blog/agents/topology` and `GET /blog/agents/{agent_key}` in `backend/app/modules/posts/agent_router.py`
- [ ] T026 [P] [US1] Implement typed topology/detail API calls and status labels in `frontend/src/api/blogAgents.ts`
- [ ] T027 [P] [US1] Build reusable semantic Agent node cards with upstream/downstream and condition summaries in `frontend/src/modules/posts/AgentNodeCard.vue`
- [ ] T028 [US1] Build the stage-based desktop topology and equivalent ordered mobile/list view with filters and anchor restoration in `frontend/src/modules/posts/AgentOrchestrationPage.vue`
- [ ] T029 [US1] Register `/blog/agents` and add “Agent 编排” to the blog navigation in `frontend/src/router/index.ts` and `frontend/src/modules/posts/BlogModuleLayout.vue`
- [ ] T030 [US1] Validate User Story 1 independently with the Scenario 1 steps in `specs/006-agent-content-management/quickstart.md`

**Checkpoint**: A read-only MVP explains the entire real execution chain without exposing secrets or allowing false reordering.

---

## Phase 4: User Story 2 - 安全修改 Agent 文案与 Prompt (Priority: P1)

**Goal**: Create immutable Agent content drafts, validate them and explicitly activate/disable allowed nodes without affecting existing tasks.

**Independent Test**: Save an Editor Agent v2 draft, verify v1 remains active, reject unsafe content, activate valid v2 with impact confirmation, detect a concurrent conflict and restore v1 as new v3.

### Tests for User Story 2 (write first)

- [ ] T031 [P] [US2] Add endpoint contract tests for create/list/restore-default/restore-history/activate payloads and stable errors in `backend/tests/contract/test_blog_agent_contracts.py`
- [ ] T032 [P] [US2] Add integration tests for monotonic immutable versions, separate activation, required-node enable rules and optimistic conflicts in `backend/tests/integration/test_blog_agent_management.py`
- [ ] T033 [P] [US2] Add security tests proving unknown placeholders, credential patterns and attempts to override locked rules never persist or leak in errors/logs in `backend/tests/security/test_blog_agent_security.py`
- [ ] T034 [P] [US2] Add component tests for section editing, locked-rule display, field errors, draft state, impact confirmation and conflict recovery in `frontend/tests/component/blog-agent-editor.spec.ts`
- [ ] T035 [P] [US2] Add E2E coverage for save-without-activate, explicit activation and restore-as-new-version in `frontend/tests/e2e/blog-agent-management.spec.ts`

### Implementation for User Story 2

- [ ] T036 [US2] Implement monotonic version creation, immutable reads, history restore and system-default copy in `backend/app/modules/posts/agent_service.py`
- [ ] T037 [US2] Implement activation impact calculation, dependency compatibility recheck, required-node protection and optimistic locking in `backend/app/modules/posts/agent_service.py`
- [ ] T038 [US2] Add version list/create/restore/default and activation endpoints with ActivityLog safe summaries in `backend/app/modules/posts/agent_router.py`
- [ ] T039 [P] [US2] Add version/activation/restore API methods and structured validation error mapping in `frontend/src/api/blogAgents.ts`
- [ ] T040 [US2] Build manifest-driven editable sections, locked safety panels, local dirty state and draft save flow in `frontend/src/modules/posts/AgentEditorPage.vue`
- [ ] T041 [US2] Build immutable version timeline, active/draft/default markers, restore actions and field-level comparison in `frontend/src/modules/posts/AgentVersionsPage.vue`
- [ ] T042 [US2] Register Agent edit/version child routes and preserve topology return anchors in `frontend/src/router/index.ts`
- [ ] T043 [US2] Add activation/disable impact confirmation and version-conflict recovery to `frontend/src/modules/posts/AgentEditorPage.vue`
- [ ] T044 [US2] Validate User Story 2 independently with the Scenario 2 steps in `specs/006-agent-content-management/quickstart.md`

**Checkpoint**: Users can safely experiment with text; only explicit valid activation affects future submissions.

---

## Phase 5: User Story 3 - 在 Agent 位置管理关联 Skill 与能力 (Priority: P2)

**Goal**: Put existing Blog Skills and safe capability descriptors at the Agent nodes that actually use them.

**Independent Test**: From Logic Agent, distinguish and open the existing content Skill and `visualize` capability; after capability disable/health failure, see the true skip/degrade/block state without any secret configuration.

### Tests for User Story 3 (write first)

- [ ] T045 [P] [US3] Add unit tests for capability public-field allowlist, health status normalization and skip/degrade/block resolution in `backend/tests/unit/test_blog_agent_manifest.py`
- [ ] T046 [P] [US3] Add integration tests proving topology references existing BlogSkill IDs/versions without copying and respects owner filtering in `backend/tests/integration/test_blog_agent_management.py`
- [ ] T047 [P] [US3] Add security response/log tests for endpoint, header, token_file, credential URL and provider diagnostic stripping in `backend/tests/security/test_blog_agent_security.py`
- [ ] T048 [P] [US3] Add component tests for Skill-versus-capability labels, deep links, return anchors and unavailable explanations in `frontend/tests/component/blog-agents.spec.ts`

### Implementation for User Story 3

- [ ] T049 [US3] Harden `registered_capabilities` into a typed public descriptor and add bounded health/source normalization in `backend/app/modules/posts/orchestrator.py`
- [ ] T050 [US3] Merge owned current Blog Skill references and manifest capability dependencies into Agent detail/topology responses in `backend/app/modules/posts/agent_service.py`
- [ ] T051 [US3] Add Skill/capability dependency summaries and real skip/degrade/block reasons to `frontend/src/modules/posts/AgentNodeCard.vue`
- [ ] T052 [US3] Support `returnTo`/`agent` navigation without changing Skill identities or version semantics in `frontend/src/modules/posts/SkillListPage.vue` and `frontend/src/modules/posts/SkillEditorPage.vue`
- [ ] T053 [US3] Add safe capability status refresh and unknown-state fallback to `frontend/src/modules/posts/AgentOrchestrationPage.vue`
- [ ] T054 [US3] Validate User Story 3 independently with the Scenario 3 steps in `specs/006-agent-content-management/quickstart.md`

**Checkpoint**: Agent decisions, content Skills and execution capabilities are visible in one structure while retaining separate truths and security boundaries.

---

## Phase 6: User Story 4 - 预览变更并验证实际绑定 (Priority: P2)

**Goal**: Preview any accessible Agent version without formal article side effects and trace the exact orchestration snapshot used by each new formal task.

**Independent Test**: Run a draft Logic preview while broker/model states change, verify no revision/candidate is created, then submit a formal task and prove later Agent/Skill edits do not change its frozen versions or selected/skipped explanation.

### Tests for User Story 4 (write first)

- [ ] T055 [P] [US4] Add preview and run-orchestration REST/message contract tests, including identifier-only broker payloads in `backend/tests/contract/test_blog_agent_contracts.py`
- [ ] T056 [P] [US4] Add integration tests for durable preview-before-outbox, no PostRevision/PostAICandidate side effects and owned post-revision samples in `backend/tests/integration/test_blog_agent_snapshot.py`
- [ ] T057 [P] [US4] Add integration tests that formal submission atomically freezes manifest, Agent versions, Skill version, safety version and safe capability hash in `backend/tests/integration/test_blog_agent_snapshot.py`
- [ ] T058 [P] [US4] Add reliability tests for broker outage, duplicate delivery, model timeout, capability failure and idempotent execution-result recording in `backend/tests/reliability/test_blog_agent_preview.py`
- [ ] T059 [P] [US4] Add unit tests for fixed prompt composition order and proof that Worker assembly uses snapshot versions instead of current activation in `backend/tests/unit/test_blog_prompt_assembly.py`
- [ ] T060 [P] [US4] Add component tests for preview status/result/error and formal task selected/skipped/version trace in `frontend/tests/component/blog-agent-editor.spec.ts` and `frontend/tests/component/blog-management.spec.ts`
- [ ] T061 [P] [US4] Add E2E coverage for draft preview, article-count invariance and formal task trace after config changes in `frontend/tests/e2e/blog-agent-management.spec.ts`

### Implementation for User Story 4

- [ ] T062 [US4] Implement durable preview creation/read lifecycle, sample ownership, input hashing and safe result serialization in `backend/app/modules/posts/agent_service.py`
- [ ] T063 [US4] Add preview create/get endpoints that transact Preview, AsyncJob and Outbox before dispatch in `backend/app/modules/posts/agent_router.py`
- [ ] T064 [US4] Register `blog.agent_preview.v1` routing and idempotent Worker execution using preview IDs only in `backend/app/workers/tasks/blog.py`
- [ ] T065 [US4] Extract fixed-layer prompt assembly that accepts manifest/Agent/Skill snapshots and never expands unknown placeholders in `backend/app/modules/posts/orchestrator.py`
- [ ] T066 [US4] Create BlogOrchestrationSnapshot in the existing optimize submission transaction and return legacy markers for old runs in `backend/app/modules/posts/ai_service.py` and `backend/app/modules/posts/agent_service.py`
- [ ] T067 [US4] Make the formal Worker load immutable snapshot configuration, record selected/skipped/capability/quality results idempotently and stop reading current Agent activation in `backend/app/workers/tasks/blog.py`
- [ ] T068 [US4] Add `GET /blog/ai-runs/{run_id}/orchestration` with owner checks and `legacy_incomplete` compatibility in `backend/app/modules/posts/agent_router.py`
- [ ] T069 [P] [US4] Add typed preview and run-snapshot API methods/polling helpers in `frontend/src/api/blogAgents.ts`
- [ ] T070 [US4] Build temporary/post-revision sample selection, async progress and safe result display in `frontend/src/modules/posts/AgentPreviewPanel.vue`
- [ ] T071 [US4] Integrate preview without auto-activation into `frontend/src/modules/posts/AgentEditorPage.vue`
- [ ] T072 [US4] Add frozen orchestration versions, selected/skipped reasons, capability and quality outcomes to `frontend/src/modules/posts/BlogJobDetailPage.vue`
- [ ] T073 [US4] Validate User Story 4 independently with the Scenario 4 steps in `specs/006-agent-content-management/quickstart.md`

**Checkpoint**: Prompt experiments have no formal content side effects, and every new formal run is reproducible and explainable.

---

## Phase 7: User Story 5 - 管理变更影响与审计 (Priority: P3)

**Goal**: Compare and restore versions, handle manifest upgrades explicitly and audit configuration operations without storing private Prompt text.

**Independent Test**: Compare two versions, simulate manifest/default drift, observe needs-revalidation, restore system default as a new version and inspect a safe activity record.

### Tests for User Story 5 (write first)

- [ ] T074 [P] [US5] Add unit tests for base manifest/default hash drift, current/needs-revalidation/deprecated states and safe default copy in `backend/tests/unit/test_blog_agent_manifest.py`
- [ ] T075 [P] [US5] Add integration tests for version comparison, impact summaries, safe ActivityLog metadata and referenced-version retention in `backend/tests/integration/test_blog_agent_management.py`
- [ ] T076 [P] [US5] Add security tests proving ActivityLog, errors and structured logs contain no complete Prompt or preview content in `backend/tests/security/test_blog_agent_security.py`
- [ ] T077 [P] [US5] Add component tests for diff highlights, compatibility states, impact summaries, default restore and activity display in `frontend/tests/component/blog-agent-editor.spec.ts`

### Implementation for User Story 5

- [ ] T078 [US5] Implement compatibility state derivation, version diff allowlist, activation impact summary and referenced-draft retention rules in `backend/app/modules/posts/agent_service.py`
- [ ] T079 [US5] Add version comparison and impact endpoints plus safe ActivityLog events for create/activate/disable/restore in `backend/app/modules/posts/agent_router.py`
- [ ] T080 [US5] Surface manifest drift, needs-revalidation/deprecated status and affected branch summaries in `frontend/src/modules/posts/AgentVersionsPage.vue`
- [ ] T081 [US5] Add field-level diff, current/default restore confirmation and safe activity timeline to `frontend/src/modules/posts/AgentEditorPage.vue`
- [ ] T082 [US5] Validate User Story 5 independently with the Scenario 5 steps in `specs/006-agent-content-management/quickstart.md`

**Checkpoint**: Long-term Agent content maintenance is reversible, upgrade-aware and safely auditable.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Verify performance, complete regression coverage and leave operator documentation for the whole feature.

- [ ] T083 [P] Add topology/save/activation/snapshot latency budgets and bounded version pagination tests in `backend/tests/performance/test_blog_agent_management.py`
- [ ] T084 [P] Add frontend loading, empty, partial capability and recoverable error states to `frontend/src/modules/posts/AgentOrchestrationPage.vue` and `frontend/src/modules/posts/AgentEditorPage.vue`
- [ ] T085 [P] Document manifest upgrades, safe capability fields, preview cleanup and diagnostic log queries in `docs/operations.md`
- [ ] T086 Verify no-user-override compatibility with the existing orchestrator, Blog Skill, candidate, task/SSE and public post regression suites in `backend/tests/unit/test_blog_orchestrator.py`, `backend/tests/integration/test_blog_ai_pipeline.py`, and `frontend/tests/component/blog-skills.spec.ts`
- [ ] T087 Run migration upgrade/downgrade/upgrade and the complete ownership, CSRF, secret-leak, broker-outage and snapshot-nondrift matrix from `specs/006-agent-content-management/quickstart.md`
- [ ] T088 Run backend lint/type/test, frontend lint/type/component/E2E, Compose health checks and one internal article end-to-end optimization; record results in `specs/006-agent-content-management/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: starts immediately.
- **Phase 2 Foundational**: depends on Phase 1 and blocks all user stories.
- **US1 (Phase 3)**: depends only on Phase 2; recommended MVP.
- **US2 (Phase 4)**: depends only on Phase 2, but integrates its routes into the US1 topology when both are selected.
- **US3 (Phase 5)**: depends on Phase 2; UI delivery is clearest after US1, while backend safety work can proceed independently.
- **US4 (Phase 6)**: depends on Phase 2 and consumes version/activation behavior from US2 for draft previews; formal builtin snapshots can be implemented independently.
- **US5 (Phase 7)**: depends on US2 version lifecycle and is best delivered after US4 adds task references.
- **Polish (Phase 8)**: depends on all selected stories.

### User Story Completion Order

```text
Foundation
├── US1 read-only topology (MVP)
├── US2 versioned edit/activation ──┬── US4 preview + formal snapshots ── US5 governance
│                                  └── US3 Skill/capability placement
└── US3 backend capability safety can begin independently
```

### Within Each User Story

- Contract/unit/integration/security/component/E2E tests are written and observed failing before implementation.
- Backend domain logic precedes endpoints; endpoints precede UI integration.
- Immutable data and ownership checks precede background dispatch.
- Each story ends with its independent quickstart scenario before the next story is considered complete.

## Parallel Opportunities

- T002–T004 can run in parallel after T001 defines shared contract fixtures.
- T006–T010 target independent test files and can run in parallel; T013/T014 can proceed in parallel after their tests exist.
- For each story, backend contract/integration tests and frontend component/E2E tests are parallelizable before implementation.
- US1 and US2 backend work can start in parallel after Phase 2; US3 backend safety can run alongside both.
- US4 reliability tests, prompt unit tests and frontend tests are independent preparations before snapshot/Worker integration.
- T083–T085 can run in parallel before final full-suite gates.

## Parallel Examples

### User Story 1

```text
Task T020: topology contract tests in backend/tests/contract/test_blog_agent_contracts.py
Task T022: topology component tests in frontend/tests/component/blog-agents.spec.ts
Task T023: responsive/accessibility E2E in frontend/tests/e2e/blog-agent-management.spec.ts
```

### User Story 2

```text
Task T032: immutable version and activation integration tests
Task T033: unsafe Prompt and log-leak security tests
Task T034: editor component tests
```

### User Story 4

```text
Task T056: durable preview/no-side-effect integration tests
Task T058: broker/model/capability reliability tests
Task T059: fixed prompt composition unit tests
Task T060: frontend preview/task trace component tests
```

## Implementation Strategy

### MVP First

1. Complete Phase 1 contracts and Phase 2 foundation.
2. Deliver US1 read-only, true execution topology.
3. Stop and validate Scenario 1 on desktop, 360px, keyboard and screen reader.
4. Deploy internally if desired; this already makes current Agent/Prompt/Skill placement understandable without changing runtime behavior.

### Incremental Delivery

1. **MVP**: US1 — see and understand the real chain.
2. **Safe authoring**: US2 — versioned drafts and explicit activation.
3. **Contextual dependencies**: US3 — existing Skills and safe capabilities at their execution positions.
4. **Proof loop**: US4 — isolated preview and exact formal-run snapshots.
5. **Long-term governance**: US5 — comparison, upgrade drift, restore and audit.

## Task Summary

- Total tasks: 88
- Setup: 5
- Foundational: 14
- US1: 11
- US2: 14
- US3: 10
- US4: 19
- US5: 9
- Polish: 6
- Suggested MVP: Phases 1–3 through T030
- Format validation target: every executable item starts with `- [ ] TNNN`, user-story tasks include `[USn]`, and every item names an exact file path.
