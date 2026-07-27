# Tasks: 日历事件快捷操作与视觉优化

**Input**: Design documents from `/specs/004-calendar-event-actions/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Tests are required by the project constitution. Every user-story phase lists tests before the implementation tasks they validate.

**Organization**: Tasks are grouped by user story so status actions, event notes, and visual hierarchy can be implemented and accepted as independent increments.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on an incomplete task in the same phase.
- **[Story]**: Maps the task to User Story 1, 2, or 3 from spec.md.
- Every task includes exact repository-relative file paths.

## Phase 1: Setup (Shared Contract and Test Infrastructure)

**Purpose**: Wire the feature design contracts and reusable image fixtures into the existing test infrastructure.

- [ ] T001 [P] Add YAML/ref validation for the feature OpenAPI and AsyncAPI documents in `backend/tests/contract/test_calendar_event_actions_contracts.py`
- [ ] T002 [P] Add valid, corrupt, unsupported, and GPS-bearing task-note image fixtures in `backend/tests/conftest.py`

---

## Phase 2: Foundational (Blocking Data and Contract Changes)

**Purpose**: Establish the schema and shared versioned contracts required by both event-state and note-image stories.

**⚠️ CRITICAL**: Complete this phase before starting any user-story implementation.

- [ ] T003 Add failing migration/head-drift coverage for reminder purpose/anchor, `task_notes`, `task_note_assets`, indexes, constraints, and `task_note_image` upload purpose in `backend/tests/integration/test_migrations.py`
- [x] T004 Implement reversible migration `0009_calendar_event_actions` with reminder extensions, note/asset tables, partial uniqueness, and upload-purpose constraint replacement in `backend/alembic/versions/0009_calendar_event_actions.py`
- [x] T005 Implement matching ORM models and constraints in `backend/app/models/tasks.py`, `backend/app/models/scheduling.py`, `backend/app/models/voice.py`, and `backend/app/models/__init__.py`
- [ ] T006 Merge the approved feature REST/message schemas into the project-wide contract sources in `specs/001-personal-life-os/contracts/openapi.yaml` and `specs/001-personal-life-os/contracts/events.asyncapi.yaml`

**Checkpoint**: Migration upgrades and downgrades cleanly, ORM metadata has no drift, and shared contracts contain every feature boundary.

---

## Phase 3: User Story 1 - 快速调整事件状态 (Priority: P1) 🎯 MVP

**Goal**: Let desktop and mobile users open an event popover, toggle completion/importance, retain completed events in the week, and manage one idempotent four-hour email reminder.

**Independent Test**: On desktop and mobile, open one scheduled event, toggle completed and important on/off, reload, move the event, and verify emoji/style persistence plus correct reminder create/reschedule/cancel behavior without duplicate email.

### Tests for User Story 1 (write first and verify failure)

- [ ] T007 [P] [US1] Add pure rule tests for start-minus-four-hours, less-than-four-hours, missing/past start, reschedule, cancellation, and sent-reminder idempotency in `backend/tests/unit/test_important_reminder_rules.py`
- [ ] T008 [P] [US1] Add REST contract tests for status/importance patches, optimistic conflicts, reminder summaries, and completed events in week responses in `backend/tests/contract/test_calendar_event_actions_api.py`
- [ ] T009 [P] [US1] Add integration tests for reversible completion, completed-event calendar visibility, important reminder lifecycle, activity log, and Outbox atomicity in `backend/tests/integration/test_calendar_event_actions.py` and `backend/tests/integration/test_important_reminders.py`
- [ ] T010 [P] [US1] Add failure-path tests for SMTP unconfigured/failure, worker redelivery, and duplicate reminder prevention in `backend/tests/reliability/test_calendar_event_action_failures.py`
- [ ] T011 [P] [US1] Add component tests for desktop click/mobile tap, popover focus/close behavior, state toggles, combined emoji/important state, and error rollback in `frontend/tests/component/calendar-event-actions.spec.ts`
- [ ] T012 [P] [US1] Add a failing Playwright journey for popover state persistence and reminder feedback in `frontend/tests/e2e/calendar-event-actions.spec.ts`

### Implementation for User Story 1

- [ ] T013 [US1] Implement dedicated `important_start_4h` scheduling, stable idempotency, reschedule/cancel rules, and delivery-derived summaries in `backend/app/modules/notifications/reminder_service.py`
- [ ] T014 [US1] Make completion reversible, clear/set `completed_at`, synchronize important reminders in the task transaction, and retain completed scheduled events in `backend/app/modules/tasks/service.py` and `backend/app/modules/tasks/calendar_service.py`
- [ ] T015 [US1] Expose reminder summaries and state mutations through owned, version-checked responses in `backend/app/modules/tasks/schemas.py`, `backend/app/modules/tasks/router.py`, and `backend/app/modules/tasks/calendar_router.py`
- [ ] T016 [P] [US1] Extend frontend Task/reminder types and mutation helpers without bypassing the shared changed signal in `frontend/src/api/tasks.ts`, `frontend/src/api/calendar.ts`, and `frontend/src/stores/tasks.ts`
- [ ] T017 [P] [US1] Add semantic important-background tokens and implement the accessible state-action popover component in `frontend/src/styles/tokens.css` and `frontend/src/modules/calendar/CalendarEventPopover.vue`
- [ ] T018 [US1] Wire FullCalendar event click/tap, popover anchoring, optimistic busy/error states, reload, and shared-store synchronization in `frontend/src/modules/calendar/CalendarPage.vue`

**Checkpoint**: User Story 1 passes independently and is a deployable MVP without event notes or past-slot styling.

---

## Phase 4: User Story 2 - 为事件添加图文备注 (Priority: P2)

**Goal**: Persist one owned event note and append multiple batches of private images with per-file success, sanitized previews, retryable failure state, and stable database associations.

**Independent Test**: Save note text plus three upload batches totaling at least twelve images, force one file and one derivative failure, reload, and verify every successful image remains ordered and associated only with the correct user/task/note.

### Tests for User Story 2 (write first and verify failure)

- [ ] T019 [P] [US2] Add REST contract tests for nullable note reads, versioned note puts, first-batch and append attachment responses, upload purpose, and protected access variants in `backend/tests/contract/test_calendar_event_actions_api.py`
- [ ] T020 [P] [US2] Add integration tests for text-only, image-only, three-batch append, stable ordering, duplicate upload rejection, partial success, and reload persistence in `backend/tests/integration/test_task_note_assets.py`
- [ ] T021 [P] [US2] Add cross-user tests for task-note read/write, foreign upload association, preview/original access, and non-disclosing errors in `backend/tests/security/test_task_note_asset_security.py`
- [ ] T022 [P] [US2] Add data-survival and idempotency tests for storage failure, association rollback, derivative retry/redelivery, and orphan cleanup in `backend/tests/reliability/test_calendar_event_action_failures.py`
- [ ] T023 [P] [US2] Add component tests for note version conflicts, multiple file selection, three append batches, per-file progress/failure/retry, and successful-item retention in `frontend/tests/component/calendar-event-note.spec.ts`
- [ ] T024 [P] [US2] Extend the Playwright journey with text-only, image-only, multi-batch, partial-failure, reload, and private preview checks in `frontend/tests/e2e/calendar-event-actions.spec.ts`

### Implementation for User Story 2

- [ ] T025 [P] [US2] Enforce `task_note_image` image MIME/size rules and expose the upload purpose in `backend/app/modules/uploads/router.py` and `backend/app/modules/uploads/service.py`
- [ ] T026 [US2] Implement owned/versioned note create-update-read, first-batch attachment, append-only association, audit, job, and Outbox transactions in `backend/app/modules/tasks/note_service.py`
- [ ] T027 [US2] Implement strict note/asset schemas, REST endpoints, preview/original authorization, and router registration in `backend/app/modules/tasks/note_router.py`, `backend/app/modules/tasks/schemas.py`, and `backend/app/main.py`
- [ ] T028 [US2] Generalize image validation/preview helpers and add idempotent task-note preview processing with durable job transitions in `backend/app/modules/captures/upload_service.py` and `backend/app/workers/tasks/images.py`
- [ ] T029 [P] [US2] Add ownership-safe cleanup for expired unassociated `task_note_image` uploads and schedule it through the existing maintenance cadence in `backend/app/workers/tasks/maintenance.py` and `backend/app/workers/beat_schedule.py`
- [ ] T030 [P] [US2] Add typed note/asset/access APIs and a per-file `Promise.allSettled` upload/append flow in `frontend/src/api/taskNotes.ts` and `frontend/src/modules/calendar/useTaskNoteUploads.ts`
- [ ] T031 [US2] Implement the note editor with text/image-only save, repeated multiple selection, ordered previews, progress, failure, and retry UI in `frontend/src/modules/calendar/CalendarEventNoteEditor.vue`
- [ ] T032 [US2] Integrate note loading/editing into the event popover while preserving saved state when the panel closes or a file fails in `frontend/src/modules/calendar/CalendarEventPopover.vue` and `frontend/src/modules/calendar/CalendarPage.vue`

**Checkpoint**: User Story 2 passes independently; image failures do not lose note text or already accepted images.

---

## Phase 5: User Story 3 - 清晰识别事件与已流逝时间 (Priority: P3)

**Goal**: Render event title before its time range and gray elapsed time-grid cells without hiding completed/important styling or text.

**Independent Test**: Freeze time in a week containing past/current/future slots and all state combinations; verify desktop/mobile, light/dark, long-title, and one-minute boundary behavior.

### Tests for User Story 3 (write first and verify failure)

- [ ] T033 [P] [US3] Add component tests for title-before-time markup, long-title behavior, local-time past-slot classification, minute-boundary refresh, and combined visual classes in `frontend/tests/component/calendar-event-actions.spec.ts`
- [ ] T034 [P] [US3] Extend the Playwright journey with desktop/mobile and light/dark visual assertions for elapsed slots and event readability in `frontend/tests/e2e/calendar-event-actions.spec.ts`

### Implementation for User Story 3

- [ ] T035 [US3] Implement safe custom event content, title-first/time-second ordering, local-time slot class callbacks, and minute-boundary refresh in `frontend/src/modules/calendar/CalendarPage.vue`
- [ ] T036 [US3] Add scoped elapsed-grid, completed emoji, important-event, truncation, contrast, and reduced-motion styles in `frontend/src/modules/calendar/CalendarPage.vue` and `frontend/src/styles/tokens.css`

**Checkpoint**: All three stories work independently and all completion/importance/past-time combinations remain readable.

---

## Phase 6: Polish & Cross-Cutting Validation

**Purpose**: Verify accessibility, contract drift, migrations, failure recovery, and regression safety across the complete feature.

- [ ] T037 [P] Add keyboard/focus, 44px touch target, semantic-state, and note-image accessibility coverage in `frontend/tests/e2e/accessibility.spec.ts`
- [ ] T038 Run backend formatting, lint, type, feature-focused tests, full tests, and Alembic drift checks using `backend/pyproject.toml`, fixing only feature-related failures in the files named above
- [ ] T039 Run frontend lint, typecheck, component tests, production build, and calendar Playwright tests using `frontend/package.json`, fixing only feature-related failures in the files named above
- [ ] T040 Execute every manual state/reminder/note/privacy/visual scenario and record results in `specs/004-calendar-event-actions/quickstart.md`
- [ ] T041 Re-run schema-reference validation and `git diff --check`, then verify the implementation still satisfies every checked item in `specs/004-calendar-event-actions/checklists/requirements.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependency.
- **Phase 2 (Foundational)**: Depends on Phase 1 and blocks all implementation phases.
- **Phase 3 (US1)**: Depends on Phase 2; delivers the suggested MVP.
- **Phase 4 (US2)**: Depends on Phase 2. It can be developed alongside US1 after the shared migration lands, but final popover integration T032 consumes the popover shell from T017.
- **Phase 5 (US3)**: Depends on Phase 2. It can begin alongside US1/US2, but T035/T036 must merge after other `CalendarPage.vue` edits to avoid conflicting changes.
- **Phase 6 (Polish)**: Depends on every user story selected for release.

### User Story Dependency Graph

```text
Setup → Foundation → US1 (MVP)
                   ├→ US2 note service/API/worker → US2 popover integration (after US1 shell)
                   └→ US3 visual behavior (merge after CalendarPage integrations)

US1 + US2 + US3 → Polish & full validation
```

### Within Each User Story

- Write the listed tests first and confirm they fail for the intended missing behavior.
- Apply model/migration changes before services, services before routers/workers, and typed API helpers before Vue integration.
- Keep task update, reminder lifecycle, audit and Outbox writes in one transaction.
- Keep image upload completion separate from the note/asset transaction and compensate unattached expired uploads.
- Complete the independent checkpoint before considering the story done.

## Parallel Opportunities

- T001 and T002 can run together.
- In US1, T007–T012 can be authored in parallel; after backend service contracts settle, T016 and T017 can run together.
- In US2, T019–T024 can be authored in parallel; T025, T029, and T030 touch separate files and can proceed alongside the core note service after the schema exists.
- US3 tests T033/T034 can run together, and US3 can be developed alongside the backend-heavy portion of US2.
- T037 can run alongside backend validation T038 once implementation is feature-complete.

## Parallel Example: User Story 1

```text
Task T007: backend/tests/unit/test_important_reminder_rules.py
Task T008: backend/tests/contract/test_calendar_event_actions_api.py
Task T010: backend/tests/reliability/test_calendar_event_action_failures.py
Task T011: frontend/tests/component/calendar-event-actions.spec.ts
Task T012: frontend/tests/e2e/calendar-event-actions.spec.ts
```

## Parallel Example: User Story 2

```text
Task T020: backend/tests/integration/test_task_note_assets.py
Task T021: backend/tests/security/test_task_note_asset_security.py
Task T023: frontend/tests/component/calendar-event-note.spec.ts
Task T025: backend/app/modules/uploads/router.py + backend/app/modules/uploads/service.py
Task T030: frontend/src/api/taskNotes.ts + frontend/src/modules/calendar/useTaskNoteUploads.ts
```

## Implementation Strategy

### MVP First (User Story 1)

1. Complete Phase 1 and Phase 2.
2. Complete T007–T012 and confirm the new tests fail for the intended reasons.
3. Complete T013–T018.
4. Stop and validate the US1 checkpoint: desktop/mobile popover, reversible state, completed visibility, and one correct reminder.

### Incremental Delivery

1. Deliver US1 for immediate event-state value.
2. Add US2 backend note/image slice and validate it through API before integrating the editor into the popover.
3. Add US3 presentation rules after functional popover edits stabilize.
4. Complete Phase 6 and the full quickstart before release.

## Notes

- `[P]` means different files or safely separable work; it does not remove the declared phase dependencies.
- Tests are deliberately placed before implementations to satisfy Constitution Principle VII.
- Do not expose storage keys, raw provider errors, user-private note text, or image bytes in logs/messages.
- Do not change fixed-event drag rules, recurrence semantics, external calendar integration, or AI behavior in this feature.
