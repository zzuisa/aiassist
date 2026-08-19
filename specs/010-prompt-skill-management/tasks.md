# Tasks: 集中 Prompt 与 Skill 管理

**Input**: Design documents from `specs/010-prompt-skill-management/`

## Phase 1: Setup

- [X] T001 Add active plan reference and feature artefacts in `AGENTS.md` and `specs/010-prompt-skill-management/`

## Phase 2: Foundational

- [X] T002 Create versioned AI configuration persistence and Alembic migration in `backend/app/models/ai_config.py` and `backend/alembic/versions/`
- [X] T003 Create module catalog, baseline Prompt definitions and immutable safety boundary assembly in `backend/app/modules/ai_config/catalog.py`
- [X] T004 Implement profile/version resolution, validation and binding service in `backend/app/modules/ai_config/service.py`
- [X] T005 Add Pydantic schemas and protected configuration API router in `backend/app/modules/ai_config/schemas.py` and `backend/app/modules/ai_config/router.py`
- [X] T006 Register the AI configuration router and add frontend API types in `backend/app/main.py` and `frontend/src/api/aiConfig.ts`

## Phase 3: User Story 1 - 管理模块提示词 (P1)

**Goal**: Users manage module Prompt/Skill versions without code changes.

**Independent Test**: Create, activate and resolve a module configuration while preserving history and user isolation.

- [X] T007 [P] [US1] Add configuration ownership/version contract coverage in `backend/tests/contract/test_ai_config_contract.py`
- [X] T008 [P] [US1] Add service validation and immutable-boundary unit coverage in `backend/tests/unit/test_ai_config_service.py`
- [X] T009 [US1] Implement module/version list, save and activate endpoints in `backend/app/modules/ai_config/router.py`
- [X] T010 [US1] Implement AI configuration centre page and route in `frontend/src/modules/settings/AIConfigPage.vue` and `frontend/src/router/index.ts`
- [X] T011 [US1] Add module/version UI component coverage in `frontend/tests/component/ai-config.spec.ts`

## Phase 4: User Story 2 - 用 Skill 驱动 Agent 工具调用 (P1)

**Goal**: Agent has the model construct schema-constrained calls using current Skill defaults.

**Independent Test**: “最近文章” invokes `posts.list_recent` with configured default 10; explicit count overrides it; invalid calls are rejected.

- [X] T012 [P] [US2] Add conversation route tool-call/default-parameter tests in `backend/tests/integration/test_agent_skill_tool_calls.py`
- [X] T013 [US2] Extend route schema and validate model-produced tool arguments in `backend/app/modules/agent/conversation_schemas.py` and `backend/app/modules/agent/conversation_router.py`
- [X] T014 [US2] Resolve the Agent routing configuration and bind it to turns/tasks in `backend/app/modules/agent/conversation_service.py`
- [X] T015 [US2] Replace mandatory recent-article regex clarification with Skill defaults and provider-fallback handling in `backend/app/modules/agent/intents.py` and `backend/app/modules/agent/service.py`
- [X] T016 [US2] Add Agent browser coverage for default and explicit article quantities in `frontend/tests/e2e/agent-skill-articles.spec.ts`

## Phase 5: User Story 3 - 统一试运行与审计 (P2)

- [X] T017 [P] [US3] Add non-writing dry-run and binding visibility coverage in `backend/tests/integration/test_ai_config_dry_run.py`
- [X] T018 [US3] Add dry-run endpoint and safe binding serialization in `backend/app/modules/ai_config/router.py` and `backend/app/modules/ai_config/service.py`
- [X] T019 [US3] Add dry-run controls and result display in `frontend/src/modules/settings/AIConfigPage.vue`
- [X] T020 [US3] Adapt all LLM call sites to resolve versioned baseline configuration in `backend/app/modules/agent/registry.py`, `backend/app/modules/tasks/plan_service.py`, `backend/app/modules/voice/service.py`, `backend/app/workers/tasks/capture_ai.py`, and `backend/app/workers/tasks/blog.py`
- [X] T021 [US3] Preserve and map existing Blog Skill versions in `backend/app/modules/posts/skill_service.py` and `backend/app/workers/tasks/blog.py`

## Phase 6: Validation

- [X] T022 Run backend formatting, type checks and focused contract/integration tests from `backend/`
- [X] T023 Run frontend lint, typecheck, component tests and production build from `frontend/` (passed in Node 24 container)
- [X] T024 Verify the quickstart flow and record completed tasks in `specs/010-prompt-skill-management/tasks.md`

## Dependencies

- T002–T006 block all user stories.
- US2 depends on configuration resolution from US1 but can be tested against the seeded baseline.
- US3 extends the common binding service and follows US1/US2.

## Implementation Strategy

Deliver the versioned configuration service and UI first, then route Agent calls through it so the article default is configuration-driven. Finally migrate the remaining LLM callers and add dry-run/audit support.
