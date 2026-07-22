# Tasks: AI Assist 个人生活操作系统 MVP

**Input**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: REQUIRED by the project constitution. Test/contract tasks appear before the implementation they validate.

**Format**: `[ID] [P?] [Story?] Description with exact file path`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create reproducible frontend, backend, test, and deployment skeletons without business behavior.

- [ ] T001 Create the planned repository directories and placeholder package markers in `backend/app/`, `backend/tests/`, `frontend/src/`, `frontend/tests/`, and `deploy/`
- [ ] T002 Initialize Python 3.12 backend metadata, bounded dependencies, lock workflow, and CLI entry points in `backend/pyproject.toml`
- [ ] T003 Initialize Vue/TypeScript/Vite/Pinia/Router/Naive UI/FullCalendar/PWA dependencies and npm scripts in `frontend/package.json`
- [ ] T004 [P] Configure strict TypeScript, Vite aliases, Vitest, and vue-tsc in `frontend/tsconfig.json`, `frontend/vite.config.ts`, and `frontend/vitest.config.ts`
- [ ] T005 [P] Configure Ruff, mypy/pyright policy, pytest markers, and coverage thresholds in `backend/pyproject.toml`
- [ ] T006 Create non-secret configuration inventory and secret-file examples in `.env.example` and `deploy/secrets/README.md`
- [ ] T007 Create baseline Compose networks, named volumes, healthcheck placeholders, and optional `s3` profile in `compose.yaml`
- [ ] T008 [P] Create CI jobs for lint, typecheck, contract validation, unit tests, integration tests, and image builds in `.github/workflows/ci.yml`

**Checkpoint**: Both projects install from lockfiles; `docker compose config --quiet` and empty test commands pass.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build identity, configuration, database, providers, reliable messaging, durable jobs, SSE, and the responsive shell.

**CRITICAL**: No user story implementation begins before this phase passes.

### Foundational tests and contracts (write first)

- [ ] T009 [P] Add automated validation for OpenAPI, AsyncAPI, and all JSON Schemas in `backend/tests/contract/test_design_contracts.py`
- [ ] T010 [P] Add empty-database upgrade, current-head, and model-drift tests in `backend/tests/integration/test_migrations.py`
- [ ] T011 [P] Add authentication, refresh rotation, CSRF, generic login error, and cross-user ownership tests in `backend/tests/integration/test_auth.py`
- [ ] T012 [P] Add outbox crash-boundary, duplicate delivery, lease recovery, and idempotency tests in `backend/tests/integration/test_outbox.py`
- [ ] T013 [P] Add durable job transition, SSE replay, expired-cursor snapshot, Redis-outage, and user-isolation tests in `backend/tests/integration/test_job_events.py`
- [ ] T014 [P] Add frontend auth refresh, logout clearing, EventSource dedupe, and reconnect store tests in `frontend/tests/component/foundation.spec.ts`

### Foundational implementation

- [ ] T015 Implement typed settings, secret-file loading, environment validation, and dependency health states in `backend/app/core/config.py`
- [ ] T016 [P] Implement RFC 9457 errors, W3C trace propagation, safe structured logging, and request limits in `backend/app/core/errors.py` and `backend/app/core/observability.py`
- [ ] T017 Implement SQLAlchemy engine/session transaction boundaries and declarative base conventions in `backend/app/db/session.py` and `backend/app/db/base.py`
- [ ] T018 Implement foundational models for users, refresh sessions, categories, tags, outbox, consumer receipts, idempotency, jobs, job events, and activity logs in `backend/app/models/foundation.py`
- [ ] T019 Create and review the foundational Alembic migration with citext, constraints, indexes, and downgrade policy in `backend/alembic/versions/0001_foundation.py`
- [ ] T020 Implement Argon2id password verification, JWT issue/validation, refresh-family rotation, revocation, CSRF, and login throttling in `backend/app/modules/auth/service.py`
- [ ] T021 Implement login/refresh/logout/me routes and ownership-aware current-user dependencies in `backend/app/modules/auth/router.py` and `backend/app/api/dependencies.py`
- [ ] T022 [P] Define provider-neutral LLM, speech, storage, and mail protocols plus stable errors in `backend/app/services/llm/base.py`, `backend/app/services/speech/base.py`, `backend/app/services/storage/base.py`, and `backend/app/services/mail/base.py`
- [ ] T023 Implement streamed local private storage, temporary/final object keys, hash validation, and authorized X-Accel responses in `backend/app/services/storage/providers/local.py`
- [ ] T024 Implement Celery configuration, explicit queue routes, quorum/confirm settings, retry policy, and trace headers in `backend/app/workers/celery_app.py`
- [ ] T025 Implement transactional outbox append/claim/lease/confirm/reconcile logic and standalone process entry point in `backend/app/services/outbox/publisher.py`
- [ ] T026 Implement durable async job state machine, append-only event writes, Redis wakeups, DB polling fallback, and SSE response in `backend/app/modules/jobs/service.py` and `backend/app/modules/jobs/sse.py`
- [ ] T027 Implement typed fetch, Problem Details mapping, CSRF/refresh retry, auth store, and route guards in `frontend/src/api/client.ts`, `frontend/src/stores/auth.ts`, and `frontend/src/router/index.ts`
- [ ] T028 Implement responsive desktop/mobile app shell, semantic theme tokens, navigation, safe-area handling, global EventSource, and base jobs store in `frontend/src/app/AppShell.vue`, `frontend/src/styles/tokens.css`, and `frontend/src/stores/jobs.ts`

**Checkpoint**: Authentication and SSE work against real PostgreSQL/Redis; broker outage still permits an authenticated base transaction plus pending outbox row.

---

## Phase 3: User Story 1 - 安全进入个人空间并可靠记录 (Priority: P1) 🎯 Increment 1

**Goal**: Login, create/edit/complete private tasks, and use the Today dashboard even when AI/workers are down.

**Independent Test**: Stop AI/workers, log in, create a task, reload it, complete it, and verify another user cannot read/search it.

### Tests for User Story 1

- [ ] T029 [P] [US1] Add task CRUD, validation, optimistic version, completion, deletion, and ownership contract tests in `backend/tests/contract/test_tasks_api.py`
- [ ] T030 [P] [US1] Add current-task selection, Today aggregation, and AI/broker unavailable durability tests in `backend/tests/integration/test_today_tasks.py`
- [ ] T031 [P] [US1] Add task list, quick input, detail drawer, unsaved-input retention, and state token component tests in `frontend/tests/component/tasks.spec.ts`
- [ ] T032 [US1] Add login → quick task → edit → complete → reload Playwright journey in `frontend/tests/e2e/tasks-today.spec.ts`

### Implementation for User Story 1

- [ ] T033 [P] [US1] Implement task, reminder stub, and task-tag models with fixed-event checks and habit-source uniqueness in `backend/app/models/tasks.py`
- [ ] T034 [US1] Create task/task-tag Alembic migration and query indexes in `backend/alembic/versions/0002_tasks.py`
- [ ] T035 [US1] Implement task create/update/complete/delete, optimistic concurrency, current-task ranking, and activity/outbox writes in `backend/app/modules/tasks/service.py`
- [ ] T036 [US1] Implement task CRUD endpoints and version-conflict Problem Details in `backend/app/modules/tasks/router.py`
- [ ] T037 [US1] Implement Today aggregation query with task, timeline, overdue, placeholder habit/suggestion/capture/job sections in `backend/app/modules/tasks/today.py`
- [ ] T038 [P] [US1] Implement tasks store, filters, list cards, quick input, and detail drawer in `frontend/src/modules/tasks/` and `frontend/src/stores/tasks.ts`
- [ ] T039 [US1] Implement the mobile-first Today page and one-current-task presentation in `frontend/src/modules/today/TodayPage.vue`

**Checkpoint**: US1 is deployable independently and satisfies durable text capture without AI.

---

## Phase 4: User Story 2 - 从今日工作台完成任务并安排一周 (Priority: P1)

**Goal**: Week calendar drag/resize, conflicts, fixed-event protection, schedule preview/apply, and reliable in-app/email reminders.

**Independent Test**: Schedule three tasks around a fixed event, observe conflict, preview concrete AI changes, apply selected non-stale items, and receive an important reminder while heavy work runs.

### Tests for User Story 2

- [ ] T040 [P] [US2] Add week calendar, reminder, preview, apply, partial-conflict, and fixed-event OpenAPI tests in `backend/tests/contract/test_calendar_api.py`
- [ ] T041 [P] [US2] Add schedule conflict, stale version, fixed event, DST, preview expiry, and undo domain tests in `backend/tests/unit/test_scheduling.py`
- [ ] T042 [P] [US2] Add due-reminder claim, duplicate scan, SMTP 4xx/5xx, critical routing, and send-attempt tests in `backend/tests/integration/test_reminders.py`
- [ ] T043 [P] [US2] Add FullCalendar drag/resize revert, fixed-event, touch fallback, and preview overlay component tests in `frontend/tests/component/calendar.spec.ts`

### Implementation for User Story 2

- [ ] T044 [US2] Implement reminders, schedule previews, notifications, and delivery-attempt models in `backend/app/models/scheduling.py` and `backend/app/models/notifications.py`
- [ ] T045 [US2] Create reminder/preview/notification Alembic migration with due and idempotency indexes in `backend/alembic/versions/0003_scheduling_notifications.py`
- [ ] T046 [P] [US2] Implement week queries, interval conflict detection, fixed-event rules, and manual undo activity in `backend/app/modules/tasks/calendar_service.py`
- [ ] T047 [US2] Implement grounded schedule preview generation, source-version snapshots, expiry, selective apply, and rejection details in `backend/app/modules/tasks/schedule_service.py`
- [ ] T048 [P] [US2] Implement due reminder scanning, unique delivery creation, critical/notification outbox routing, and task-time rescheduling in `backend/app/modules/notifications/reminder_service.py`
- [ ] T049 [US2] Implement SMTP MailGateway with required TLS, stable errors, bounded retry, and delivery audit in `backend/app/services/mail/providers/smtp.py` and `backend/app/workers/tasks/notifications.py`
- [ ] T050 [US2] Implement calendar, schedule-preview/apply, and reminder endpoints in `backend/app/modules/tasks/calendar_router.py`
- [ ] T051 [US2] Implement FullCalendar week/day mobile modes, unscheduled drawer, drag/resize pending state, revert, and conflict UI in `frontend/src/modules/calendar/CalendarPage.vue`
- [ ] T052 [US2] Implement concrete schedule preview drawer, selective/batch apply, stale feedback, reminder editor, and notification badges in `frontend/src/modules/calendar/SchedulePreviewDrawer.vue`
- [ ] T053 [US2] Add end-to-end fixed-event, drag rollback, selective preview apply, and critical reminder flow in `frontend/tests/e2e/calendar-reminders.spec.ts`

**Checkpoint**: Calendar changes are version-safe; preview and apply are separate; fixed events have zero AI moves.

---

## Phase 5: User Story 3 - 建立习惯并每日打卡 (Priority: P1)

**Goal**: Create recurring habits, idempotently generate today's tasks, check in/time/skip, and view streak/rate/heatmap.

**Independent Test**: Create a daily habit, trigger generation twice, complete and skip on different dates, and verify one task per day plus correct statistics.

### Tests for User Story 3

- [ ] T054 [P] [US3] Add recurrence, local-date/DST generation, duplicate scheduler, check-in, skip, and streak tests in `backend/tests/integration/test_habits.py`
- [ ] T055 [P] [US3] Add habit card, timer, skip reason, statistics, and heatmap component tests in `frontend/tests/component/habits.spec.ts`
- [ ] T056 [US3] Add create → generate → check in → skip → statistics Playwright journey in `frontend/tests/e2e/habits.spec.ts`

### Implementation for User Story 3

- [ ] T057 [P] [US3] Implement habit and habit-log models, recurrence validation, and task relation in `backend/app/models/habits.py`
- [ ] T058 [US3] Create habits Alembic migration with `(user_id, habit_id, local_date)` uniqueness in `backend/alembic/versions/0004_habits.py`
- [ ] T059 [US3] Implement habit CRUD, timer/check-in/skip, statistics, and idempotent task generation in `backend/app/modules/habits/service.py`
- [ ] T060 [US3] Implement Beat scan and schedule-queue habit generation tasks in `backend/app/workers/tasks/habits.py` and `backend/app/workers/beat_schedule.py`
- [ ] T061 [US3] Implement habit CRUD/check-in/skip/stats endpoints and Today integration in `backend/app/modules/habits/router.py`
- [ ] T062 [US3] Implement habit cards, timer, skip sheet, statistics, heatmap, and editor in `frontend/src/modules/habits/`

**Checkpoint**: Habit generation is idempotent across duplicate Beat/worker executions and respects user timezone.

---

## Phase 6: User Story 4 - 用语音快速生成待确认任务 (Priority: P1)

**Goal**: Persist audio first, transcribe and parse asynchronously through gateways, then create exactly one edited formal entity after confirmation.

**Independent Test**: Record the landlord reminder phrase, interrupt transcription once, retry, edit the candidate, confirm it, and verify one task/reminder with source relation.

### Tests for User Story 4

- [ ] T063 [P] [US4] Validate strict `voice-task.v1` success, unknown fields, invalid dates, and malformed Provider output in `backend/tests/contract/test_voice_schema.py`
- [ ] T064 [P] [US4] Add upload-first, Provider timeout, checkpoint retry, waiting_user, double-confirm, and source-relation tests in `backend/tests/integration/test_voice_pipeline.py`
- [ ] T065 [P] [US4] Add recorder permission, upload progress, failure retention, and confirmation-card edit tests in `frontend/tests/component/voice.spec.ts`
- [ ] T066 [US4] Add mobile voice record → wait → edit → confirm Playwright journey with fake providers in `frontend/tests/e2e/voice.spec.ts`

### Implementation for User Story 4

- [ ] T067 [P] [US4] Implement upload-session, voice-record, and audio-asset models with confirm state constraints in `backend/app/models/voice.py`
- [ ] T068 [US4] Create upload/voice Alembic migration and state indexes in `backend/alembic/versions/0005_voice_uploads.py`
- [ ] T069 [P] [US4] Implement OpenAI Whisper, faster-whisper, and generic cloud adapters behind SpeechGateway in `backend/app/services/speech/providers/`
- [ ] T070 [P] [US4] Implement OpenAI, Anthropic, and Ollama structured-output adapters and scenario routing in `backend/app/services/llm/providers/` and `backend/app/services/llm/gateway.py`
- [ ] T071 [US4] Implement transcribe → strict parse → waiting_user pipeline, checkpoints, job events, and safe retries in `backend/app/workers/tasks/voice.py`
- [ ] T072 [US4] Implement upload, voice status/retry, and idempotent confirm-to-task endpoints in `backend/app/modules/voice/router.py` and `backend/app/modules/voice/service.py`
- [ ] T073 [US4] Implement MediaRecorder flow, streamed upload, task-center linkage, and persistent retry state in `frontend/src/modules/voice/VoiceRecorder.vue`
- [ ] T074 [US4] Implement schema-driven confirmation card, timezone display, edited submit, and discard flow in `frontend/src/modules/voice/VoiceConfirmDrawer.vue`

**Checkpoint**: Audio and transcript survive Provider failure; dates/reminders never create records before confirmation.

---

## Phase 7: User Story 5 - 拍照收藏并异步补全信息 (Priority: P1)

**Goal**: Save private originals immediately, create sanitized derivatives, analyze metadata, show progress, and keep user facts distinct from AI suggestions.

**Independent Test**: Upload a kitchen-tool JPEG containing EXIF GPS while AI is down, view the saved card, recover processing, edit suggested fields, and verify public/display derivatives contain no location metadata.

### Tests for User Story 5

- [ ] T075 [P] [US5] Add upload size, magic-byte, MIME mismatch, pixel bomb, path/key, ownership, and orphan-cleanup tests in `backend/tests/integration/test_upload_security.py`
- [ ] T076 [P] [US5] Add orientation-before-strip, derivative EXIF/GPS removal, deterministic variants, hash duplicate, and worker-redelivery tests in `backend/tests/integration/test_image_pipeline.py`
- [ ] T077 [P] [US5] Add strict capture-analysis schema, confidence, AI/user provenance, and no-user-overwrite tests in `backend/tests/contract/test_capture_analysis.py`
- [ ] T078 [P] [US5] Add capture list/filter/detail/convert and protected-asset API tests in `backend/tests/contract/test_captures_api.py`
- [ ] T079 [P] [US5] Add quick-photo, waterfall/list, processing card, provenance form, and asset-carousel component tests in `frontend/tests/component/captures.spec.ts`
- [ ] T080 [US5] Add mobile photo → saved pending → SSE ready → edit facts → convert Todo Playwright journey in `frontend/tests/e2e/captures.spec.ts`

### Implementation for User Story 5

- [ ] T081 [P] [US5] Implement capture, asset, AI-tag, relation, and provenance-aware fields in `backend/app/models/captures.py` and `backend/app/models/relations.py`
- [ ] T082 [US5] Create capture/assets/relations Alembic migration with hash, storage, filter, and same-user constraints in `backend/alembic/versions/0006_captures.py`
- [ ] T083 [US5] Implement streaming upload validation, temporary/final object compensation, protected access, and orphan reconciliation in `backend/app/modules/captures/upload_service.py`
- [ ] T084 [US5] Implement capture create/update/filter/detail/convert, user-over-AI merge rules, and relation checks in `backend/app/modules/captures/service.py`
- [ ] T085 [US5] Implement upload/capture/asset-access/convert endpoints in `backend/app/modules/captures/router.py`
- [ ] T086 [US5] Implement hash → EXIF/orient → sanitized original → thumbnail/WebP → OCR task pipeline with versioned keys in `backend/app/workers/tasks/images.py`
- [ ] T087 [US5] Implement capture classification/tagging through strict LLM schema and suggestion persistence in `backend/app/workers/tasks/capture_ai.py`
- [ ] T088 [P] [US5] Implement camera/file quick-add, upload progress, and durable pending card insertion in `frontend/src/modules/captures/CaptureQuickAdd.vue`
- [ ] T089 [US5] Implement responsive waterfall/list, filters, recent/pending/wishlist/duplicate views, and incremental asset loading in `frontend/src/modules/captures/CapturePage.vue`
- [ ] T090 [US5] Implement asset carousel, user-vs-AI provenance form, confidence labels, relations, and conversion actions in `frontend/src/modules/captures/CaptureDrawer.vue`

**Checkpoint**: The raw original is never lost to AI/image failure, while every browser/public derivative is location-sanitized.

---

## Phase 8: User Story 6 - 接收重要提醒并管理后台处理 (Priority: P1)

**Goal**: Expose durable, understandable long-task status; isolate important reminders; support safe retry/cancel and in-app notifications.

**Independent Test**: Saturate heavy work, trigger a critical reminder, kill/restart a worker, disconnect/reconnect SSE, and recover/ retry from the global task center.

### Tests for User Story 6

- [ ] T091 [P] [US6] Add job retry/cancel permission, stale-worker result, progress monotonicity, and preserved-entity tests in `backend/tests/integration/test_job_controls.py`
- [ ] T092 [P] [US6] Add critical queue under heavy saturation, retry exhaustion, DLQ, manual replay guard, and delivery audit tests in `backend/tests/integration/test_queue_reliability.py`
- [ ] T093 [P] [US6] Add task-center grouping, no-toast progress, retry/cancel, reconnect banner, and safe diagnostic detail tests in `frontend/tests/component/task_center.spec.ts`

### Implementation for User Story 6

- [ ] T094 [US6] Implement notification creation/read/list, delivery result states, and SSE notification events in `backend/app/modules/notifications/service.py` and `backend/app/modules/notifications/router.py`
- [ ] T095 [US6] Implement job list/detail/retry/cancel routes, retry policy registry, cancellation checks, and stale-result rejection in `backend/app/modules/jobs/router.py`
- [ ] T096 [US6] Implement DLQ inspection/replay CLI with explicit operator confirmation and new trace/attempt in `backend/app/cli/dlq.py`
- [ ] T097 [US6] Implement global task-center drawer with active/waiting/failed sections, business copy, actions, and trace detail in `frontend/src/components/jobs/TaskCenterDrawer.vue`
- [ ] T098 [US6] Implement notification list/badge/read actions and important reminder presentation in `frontend/src/components/notifications/NotificationCenter.vue`
- [ ] T099 [US6] Add critical-reminder under load, worker crash, SSE replay, retry, and cancel Playwright/API journey in `frontend/tests/e2e/jobs-notifications.spec.ts`

**Checkpoint**: Heavy work cannot hide or delay important reminders; Redis/Celery state loss does not erase user-visible status.

---

## Phase 9: User Story 7 - 跨模块搜索个人信息 (Priority: P2)

**Goal**: Search committed private tasks, habits, captures/OCR, tags/categories, and posts with grouped highlighted results.

**Independent Test**: Put one keyword in each content type, search it, observe every owned result and no cross-user data, including immediately committed records during derived-index delay.

### Tests for User Story 7

- [ ] T100 [P] [US7] Add multilingual keyword, trigram fallback, ranking, highlight sanitization, ownership, public-post, and fresh-record tests in `backend/tests/integration/test_search.py`
- [ ] T101 [P] [US7] Add grouped results, filters, pending-index hint, keyboard navigation, and empty-state tests in `frontend/tests/component/search.spec.ts`
- [ ] T102 [US7] Add 100k mixed-document seed and p95 search benchmark in `backend/tests/performance/test_search_100k.py`

### Implementation for User Story 7

- [ ] T103 [US7] Implement search-document model, tsvector/GIN/trigram migration, and language configuration in `backend/app/models/search.py` and `backend/alembic/versions/0007_search.py`
- [ ] T104 [US7] Implement direct committed-data search plus derived-document ranking, safe headline, grouping, and cursor pagination in `backend/app/modules/search/service.py`
- [ ] T105 [US7] Implement idempotent search refresh/delete tasks and event handlers in `backend/app/workers/tasks/search.py`
- [ ] T106 [US7] Implement `/search` route, filter validation, pending-index count, and protected thumbnail refs in `backend/app/modules/search/router.py`
- [ ] T107 [US7] Implement global search input, grouped result page, filters, highlights, thumbnails, and accessible keyboard flow in `frontend/src/modules/search/`

**Checkpoint**: Search is useful without a separate search service and never treats a derived index as an authorization boundary.

---

## Phase 10: User Story 8 - 从执行记录与收藏创作博客 (Priority: P2)

**Goal**: Create Markdown drafts from tasks/captures, review AI revisions as diffs, and explicitly publish safe public posts/RSS.

**Independent Test**: Generate a private draft from a completed Todo and capture, edit it, review/apply one AI revision, publish, read anonymously, then unpublish.

### Tests for User Story 8

- [ ] T108 [P] [US8] Add post draft/revision/base-conflict/private/public/slug/unpublish/relation API tests in `backend/tests/contract/test_posts_api.py`
- [ ] T109 [P] [US8] Add Markdown sanitization, unsafe link/image, RSS escaping, and public asset provenance tests in `backend/tests/unit/test_post_rendering.py`
- [ ] T110 [P] [US8] Add AI revision non-overwrite, source grounding, retry, and usage-log integration tests in `backend/tests/integration/test_blog_generation.py`
- [ ] T111 [P] [US8] Add editor autosave, preview, diff apply/ignore/regenerate, visibility, and conflict component tests in `frontend/tests/component/posts.spec.ts`

### Implementation for User Story 8

- [ ] T112 [P] [US8] Implement post, immutable revision, post-tag, and generic entity-relation models in `backend/app/models/posts.py`
- [ ] T113 [US8] Create posts/revisions/tags/relations migration with public slug constraints in `backend/alembic/versions/0008_posts.py`
- [ ] T114 [US8] Implement draft CRUD, user revisions, source conversion, diff/apply conflict, publish/unpublish, and activity/outbox rules in `backend/app/modules/posts/service.py`
- [ ] T115 [US8] Implement sanitized Markdown-to-HTML rendering, public post, protected/public derivative policy, and RSS generation in `backend/app/modules/posts/rendering.py`
- [ ] T116 [US8] Implement generate/optimize/translate blog tasks that create unapplied AI revisions and usage logs in `backend/app/workers/tasks/blog.py`
- [ ] T117 [US8] Implement private post/revision/generate/publish and public post/RSS routes in `backend/app/modules/posts/router.py`
- [ ] T118 [P] [US8] Implement Markdown editor, autosave/version conflict, preview, metadata, and source picker in `frontend/src/modules/posts/PostEditorPage.vue`
- [ ] T119 [US8] Implement revision diff, apply/ignore/regenerate, post list, publication confirmation, and public page in `frontend/src/modules/posts/`
- [ ] T120 [US8] Add source → draft → AI diff → publish → anonymous read → unpublish Playwright journey in `frontend/tests/e2e/posts.spec.ts`

**Checkpoint**: AI never overwrites authored Markdown; private content remains inaccessible until explicit publication.

---

## Phase 11: User Story 9 - 用 AI 助手执行有依据的操作 (Priority: P2)

**Goal**: Run grounded assistant intents and expose structured, explicit, version-checked action cards rather than pretend chat actions.

**Independent Test**: Ask to arrange a day containing a fixed event, verify grounded entity refs and concrete reasons, then apply one allowed action and confirm no unselected/fixed data changes.

### Tests for User Story 9

- [ ] T121 [P] [US9] Add grounded-query, no-result honesty, scope ownership, prompt-injection, fixed-event, stale-action, and selected-only effect tests in `backend/tests/integration/test_assistant.py`
- [ ] T122 [P] [US9] Add strict action-card/intent schemas and explicit action endpoint contract tests in `backend/tests/contract/test_assistant_api.py`
- [ ] T123 [P] [US9] Add intent launcher, result cards, grounded refs, apply/ignore/reanalyze, and no-chat-dominance component tests in `frontend/tests/component/assistant.spec.ts`

### Implementation for User Story 9

- [ ] T124 [US9] Implement intent registry, authorized context loaders, bounded provenance payloads, and no-result handling in `backend/app/modules/assistant/context.py`
- [ ] T125 [US9] Implement assistant run orchestration, strict action cards, stored source versions, and domain-service action execution in `backend/app/modules/assistant/service.py`
- [ ] T126 [US9] Implement assistant run/status/action routes and async LLM task adapters in `backend/app/modules/assistant/router.py` and `backend/app/workers/tasks/assistant.py`
- [ ] T127 [US9] Implement intent shortcuts, scope picker, structured result cards, grounded references, and explicit action buttons in `frontend/src/modules/assistant/AssistantPage.vue`
- [ ] T128 [US9] Add grounded arrange-today, fixed-event rejection, selected apply, and empty-search Playwright journey in `frontend/tests/e2e/assistant.spec.ts`

**Checkpoint**: Every applied assistant effect goes through a normal authorized domain service and can be traced to queried entity versions.

---

## Phase 12: Polish & Cross-Cutting Release Gates

**Purpose**: Make the whole MVP reproducible, recoverable, secure, accessible, observable, and ready for a personal server.

- [ ] T129 [P] Add production multi-stage images, non-root users, resource limits, health dependencies, migrate/backup services, and exact service commands in `backend/Dockerfile`, `frontend/Dockerfile`, and `compose.yaml`
- [ ] T130 [P] Add Nginx TLS/security headers, SPA fallback, route upload limits, SSE anti-buffering, rate limits, and internal asset location in `deploy/nginx/nginx.conf`
- [ ] T131 [P] Implement local backup/restore/manifest/checksum/orphan-audit commands and operator docs in `deploy/scripts/backup.sh`, `deploy/scripts/restore.sh`, and `docs/backup-restore.md`
- [ ] T132 [P] Implement installable app manifest, static-only service worker, offline notice, safe update prompt, and icon pipeline in `frontend/src/pwa/` and `frontend/vite.config.ts`
- [ ] T133 Run security tests for IDOR, CSRF, JWT claims/rotation, login rate limits, upload attacks, log redaction, private assets, and public post sanitization in `backend/tests/security/`
- [ ] T134 Run reliability tests for broker outage, outbox crash matrix, duplicate/redelivery, Worker death, Redis loss, Provider invalid output, DLQ, and restore recovery in `backend/tests/reliability/`
- [ ] T135 [P] Run accessibility and responsive tests for 360px layout, keyboard/focus, screen-reader labels, 44px targets, reduced motion, and non-color status in `frontend/tests/e2e/accessibility.spec.ts`
- [ ] T136 Run performance tests for text save, upload acceptance, SSE propagation, critical reminders under heavy load, and search p95 in `backend/tests/performance/`
- [ ] T137 Generate and diff frontend OpenAPI types, emitted Pydantic message/LLM schemas, and checked-in design contracts in `frontend/src/api/generated/` and `backend/tests/contract/test_schema_drift.py`
- [ ] T138 Add Provider configuration, queue/job diagnostics, storage migration, data retention, and update runbooks in `docs/operations.md`
- [ ] T139 Execute every quickstart smoke/failure/backup/restore step on a fresh host and record evidence in `specs/001-personal-life-os/checklists/quickstart-validation.md`
- [ ] T140 Run full lint/type/unit/contract/integration/E2E suites and cross-artifact analysis, resolving all HIGH findings in `specs/001-personal-life-os/checklists/release.md`

**Release checkpoint**: All Constitution gates, measurable success criteria, fresh-host quickstart, and restore drill pass.

---

## Dependencies & Execution Order

### Phase dependencies

```text
Setup -> Foundational -> US1
Foundational -> US5 -> US6
US1 -> US2
US1 -> US3
US1 -> US4
US1 + US5 -> US8
US1 + US3 + US5 + US8 -> US7 (full cross-module scope)
US1 + US2 + US3 + US5 + US8 -> US9
US1..US9 -> Polish/Release
```

- US5 can start after Foundational while US1–US4 progress because it owns separate files, except shared migration order must be rebased serially.
- US6's durable job core exists in Foundational; its full acceptance uses job types delivered by US2/US4/US5.
- US7 can start with available entities, but release acceptance waits for all searchable modules including posts.
- US8 needs task/capture source services but can build its own post module in parallel after their contracts stabilize.
- All migrations are created in numeric order; parallel branches must rebase and adjust revision down-links before merge.

## Parallel Opportunities by Story

| Story | Safe parallel starts after prerequisites |
|---|---|
| US1 | T029, T030, T031; then backend T035–T037 and frontend T038 can proceed after model/migration |
| US2 | T040–T043; then calendar T046, reminder T048/T049, and frontend T051 in separate files |
| US3 | T054 and T055; model T057 and UI T062 after contract agreement |
| US4 | T063–T065; speech T069, LLM T070, and frontend T073 after upload contract |
| US5 | T075–T079; image pipeline T086, AI T087, and frontend T088/T089 after models/contracts |
| US6 | T091–T093; notification backend T094 and frontend T097/T098 after job contracts |
| US7 | T100–T102; worker T105 and frontend T107 after search response contract |
| US8 | T108–T111; rendering T115, AI task T116, and frontend editor T118 after post model |
| US9 | T121–T123; context loader T124 and frontend T127 after action-card contract |

## Implementation Strategy

### First demonstrable increment

1. Complete Setup and Foundational.
2. Complete US1 only.
3. Validate reliable private text capture while AI/broker/worker dependencies are unavailable.
4. Deploy internally as a narrow Todo/Today build before adding media or AI.

### Full requested MVP

Deliver US1–US6 in priority order for the daily-management and reliable-capture core, then US7–US9 for search,
publishing, and grounded AI operations. Stop and validate every checkpoint; do not start second-phase sync/vector/Push/MCP work.

### Task completion rule

For each implementation task, its preceding test must exist and fail for the intended reason. A task is complete only
when relevant unit/contract/integration tests pass, ownership and trace behavior are verified, migrations are reviewed,
and no user content depends on AI/Celery state for survival.
