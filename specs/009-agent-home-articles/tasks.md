# Tasks: Agent 首屏与文章结果交互

## Phase 1: Setup

- [X] T001 Update feature design artifacts and active plan reference in `specs/009-agent-home-articles/` and `AGENTS.md`

## Phase 2: Foundational

- [X] T002 [P] Add article result card contract coverage in `backend/tests/contract/test_agent_article_results.py`
- [X] T003 [P] Add Agent landing-state and article-card component coverage in `frontend/tests/component/agent-home-articles.spec.ts`

## Phase 3: User Story 1 - Clean Agent landing page (P1)

**Goal**: Opening Agent does not restore unrelated history.

**Independent Test**: With historical messages persisted, mount Agent and verify no message-list request or history rendering occurs before a send.

- [X] T004 [US1] Change initial conversation store behavior in `frontend/src/stores/agentConversations.ts`
- [X] T005 [US1] Render a dedicated welcome/empty state in `frontend/src/components/agent/ConversationPanel.vue`
- [X] T006 [US1] Wire Agent page entry to the fresh-session behavior in `frontend/src/modules/agent/AgentPage.vue`

## Phase 4: User Story 2 - Interactive article results (P1)

**Goal**: Article query results can be opened from the conversation.

**Independent Test**: Render a result with two articles and open either card to its article detail route.

- [X] T007 [US2] Create reusable interactive result card in `frontend/src/components/agent/ArticleResultCard.vue`
- [X] T008 [US2] Render card results from the current conversation task in `frontend/src/modules/agent/AgentPage.vue`
- [X] T009 [US2] Verify owned article result paths in `backend/tests/contract/test_agent_article_results.py`

## Phase 5: User Story 3 - Preserve the current session (P2)

- [X] T010 [US3] Preserve only the mounted-page conversation across sends in `frontend/src/stores/agentConversations.ts`
- [X] T011 [US3] Add fresh-session Agent landing E2E coverage in `frontend/tests/e2e/agent-home-articles.spec.ts`

## Phase 6: Polish & Validation

- [X] T012 Run frontend lint, typecheck, component tests and production build from `frontend/`
- [X] T013 Run relevant backend contract tests from `backend/`
- [X] T014 Mark completed tasks and document validation in `specs/009-agent-home-articles/tasks.md`

## Dependencies

- T002–T003 precede their implementation tasks.
- US1 (T004–T006) is independent of US2, but both are needed for the complete new landing experience.
- US3 follows T004 because it verifies the fresh-session store behavior.

## Implementation Strategy

Deliver US1 first so opening Agent is immediately improved. Add US2 article cards next, then validate fresh-session behavior and production readiness with US3 and the validation tasks.

## Validation record

- Frontend: ESLint, Vue typecheck, Agent component tests (13 assertions), and production build passed on 2026-08-13.
- Backend: Ruff format/check and `tests/contract/test_agent_article_results.py` passed (1 test) on 2026-08-13.
- The E2E file covers the fresh landing state; it was added for the browser suite but not executed here because no local browser test server was started.
