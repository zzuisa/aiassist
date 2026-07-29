# Tasks: 个人信息总站博客内容管理扩展

**Input**: Design documents from `/specs/005-blog-content-management/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Tests are REQUIRED by the project constitution. Contract, unit, integration, security, reliability, performance, component and E2E tasks appear before the implementation they validate.

**Organization**: Tasks are grouped by user story so each story can be implemented, demonstrated and accepted independently after the shared foundation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and has no dependency on another incomplete task in the same phase.
- **[Story]**: Maps directly to the nine user stories in [spec.md](spec.md).
- Every task names the exact file path to modify or create.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add approved dependencies, contract assets and module entry points without changing behavior.

- [x] T001 Add Trafilatura 2.1 compatible dependency and lock metadata for URL extraction in `backend/pyproject.toml` and `backend/uv.lock` — pyproject updated (`trafilatura>=2.1,<3`); real lock is `backend/requirements.lock.txt` (no uv.lock in repo) — regenerated in-container, `+13` pins incl. `trafilatura==2.1.0`; also updated `requirements-dev.lock.txt`; verified `import trafilatura` OK
- [x] T002 [P] Add Milkdown Vue/Crepe compatible dependencies and lock metadata in `frontend/package.json` and `frontend/package-lock.json` — package.json updated (`@milkdown/crepe|kit|vue ^7.5.0`); `package-lock.json` regenerated in Node 24 container (10388→12861 lines), `npm ci` consistency verified
- [x] T003 [P] Add checked-in AI and Skill JSON schemas to the backend contract test manifest in `backend/tests/contract/test_blog_ai_schema.py`
- [x] T004 [P] Create shared blog API type modules and exports in `frontend/src/api/blogTypes.ts` and `frontend/src/api/types.ts`
- [x] T005 [P] Create the posts submodule package files for capture, Skill, taxonomy, AI and query services in `backend/app/modules/posts/__init__.py`
- [x] T006 Add blog content, extraction and word-cloud task routes without adding Worker processes in `backend/app/workers/celery_app.py` and `compose.yaml` — verified: `app.workers.tasks.blog.*` → `llm` queue (worker-heavy), no new Worker

**Checkpoint**: Dependencies resolve and existing backend/frontend builds still start before schema work.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish additive schema, full revision snapshots, shared validation, routing, settings and compatibility required by every story.

**⚠️ CRITICAL**: No user-story implementation begins until this phase passes migration, contract and existing Posts regression tests.

### Foundational tests — write and observe failure first

- [x] T007 [P] Add upgrade/backfill/public-state/downgrade migration tests in `backend/tests/integration/test_blog_content_migration.py`
- [x] T008 [P] Add OpenAPI, AsyncAPI and JSON Schema parse/drift tests in `backend/tests/contract/test_blog_content_contracts.py`
- [x] T009 [P] Add model ownership, unique-default, immutable-version and status-constraint tests in `backend/tests/unit/test_blog_models.py`
- [ ] T010 [P] Add complete Post revision snapshot, restore and optimistic-conflict tests in `backend/tests/integration/test_blog_editor_versions.py`
- [ ] T011 [P] Extend existing Posts public/publish/RSS regression coverage for additive fields in `backend/tests/contract/test_posts_api.py`

### Foundational implementation

- [x] T012 Create additive Post/PostRevision columns, all supporting tables, indexes, checks, FKs, seed/backfill and safe rollback notes in `backend/alembic/versions/0011_blog_content_management.py`
- [x] T013 Extend current Post projection and immutable PostRevision mapping while preserving publication semantics in `backend/app/models/posts.py`
- [x] T014 [P] Implement PostSource, PostContentType, taxonomy profile/alias, keyword and merge models in `backend/app/models/blog.py`
- [x] T015 [P] Implement BlogSkill, BlogSkillVersion and BlogSkillDefault models in `backend/app/models/blog.py`
- [x] T016 Implement PostAIRun, PostAICandidate, PostCandidateDecision, BlogSettings and PostWordCloudSnapshot models in `backend/app/models/blog.py`
- [x] T017 Register all feature models for migrations and test metadata in `backend/app/models/__init__.py`
- [x] T018 Refactor Post request/response and revision schemas out of the router and add strict blog DTOs in `backend/app/modules/posts/schemas.py`
- [x] T019 Implement complete snapshot creation, projection application, restore-as-new-version and selected-field path validation in `backend/app/modules/posts/service.py`
- [x] T020 [P] Implement content-class constants, content-type schema validation and initial per-user content-type seeding in `backend/app/modules/posts/content_types.py`
- [x] T021 [P] Implement safe blog settings defaults, schema validation, stricter-policy merge and invalid-reference warnings in `backend/app/modules/posts/settings_service.py`
- [x] T022 Implement base Skill version validation and deterministic manual/type/class/global matching in `backend/app/modules/posts/skill_service.py`
- [x] T023 Add strict `BlogOptimizationV1` and `BlogSkillConfigV1` Pydantic models that match checked-in schemas in `backend/app/services/llm/schemas.py`
- [x] T024 Extend generic Job serialization with blog scope, business stage and derived display status without changing global status storage in `backend/app/modules/jobs/schemas.py` and `backend/app/modules/jobs/service.py`
- [x] T025 Register additive capture, Skill, taxonomy, AI and query routers under existing `/api/v1` in `backend/app/main.py` and `backend/app/modules/posts/router.py`
- [x] T026 Add blog module layout, child navigation and lazy route records while preserving existing `/posts` compatibility in `frontend/src/modules/posts/BlogModuleLayout.vue` and `frontend/src/router/index.ts`
- [x] T027 Run and fix foundation migration, contract, model and existing Posts regression suites in `backend/tests/integration/test_blog_content_migration.py`, `backend/tests/contract/test_blog_content_contracts.py`, `backend/tests/unit/test_blog_models.py`, and `backend/tests/contract/test_posts_api.py`

**Checkpoint**: Existing Posts remain compatible; new schema and full snapshots are ready; all following stories may branch from this point.

---

## Phase 3: User Story 1 — 先保存再整理快速采集内容 (Priority: P1) 🎯 MVP-1

**Goal**: Create blank, clipboard, URL and quick records with durable original sources before extraction or AI, including usable failure fallback.

**Independent Test**: With AI and Worker consumption unavailable, save plain clipboard text, a URL and a quick note; reopen every original source and edit the draft. Restore processing and retry the URL exactly once.

### Tests for User Story 1 — write first ⚠️

- [ ] T028 [P] [US1] Add clipboard, URL, quick and blank capture request/response contract tests in `backend/tests/contract/test_blog_content_api.py`
- [ ] T029 [P] [US1] Add raw-before-processing, partial image, URL failure and retry integration tests in `backend/tests/integration/test_blog_capture.py`
- [ ] T030 [P] [US1] Add HTML/Markdown/rich/code/URL-only normalization corpus tests in `backend/tests/unit/test_blog_normalization.py`
- [ ] T031 [P] [US1] Add URL scheme, credential, DNS, IPv4/IPv6, redirect and response-limit security tests in `backend/tests/security/test_blog_url_and_ownership.py`
- [ ] T032 [P] [US1] Add broker-down, Worker-crash, duplicate-command and timeout survival tests in `backend/tests/reliability/test_blog_failure_matrix.py`
- [ ] T033 [P] [US1] Add new-source, clipboard preview, URL and quick-record component tests in `frontend/tests/component/blog-capture.spec.ts`
- [ ] T034 [P] [US1] Add capture happy/failure journey E2E coverage in `frontend/tests/e2e/blog-content-management.spec.ts`

### Implementation for User Story 1

- [ ] T035 [P] [US1] Implement server-side clipboard type validation, HTML cleaning, Markdown normalization and visible-text preservation checks in `backend/app/modules/posts/normalization.py`
- [ ] T036 [P] [US1] Implement per-hop URL canonicalization, DNS/IP SSRF checks, redirect validation, timeouts, media and streamed-size limits in `backend/app/modules/posts/url_extractor.py`
- [ ] T037 [US1] Implement transactional blank, clipboard, URL and quick capture with PostSource, first revision, Job and Outbox ordering in `backend/app/modules/posts/capture_service.py`
- [ ] T038 [US1] Implement capture, source detail, retry and protected snapshot-access endpoints in `backend/app/modules/posts/capture_router.py`
- [ ] T039 [US1] Implement idempotent Trafilatura extraction, optional private snapshot storage, partial result handling and edited-Post protection in `backend/app/workers/tasks/blog.py`
- [ ] T040 [US1] Implement capture API clients and typed error mapping in `frontend/src/api/blogCapture.ts`
- [ ] T041 [P] [US1] Implement source-selection and default-summary dialog in `frontend/src/modules/posts/PostCreateDialog.vue`
- [ ] T042 [P] [US1] Implement permission, detection, preview, URL-only switch and partial-image states in `frontend/src/modules/posts/ClipboardCreateDialog.vue`
- [ ] T043 [P] [US1] Implement URL, note, usage, saved-before-extract and fallback states in `frontend/src/modules/posts/UrlCreateDialog.vue`
- [ ] T044 [P] [US1] Implement minimal save/continue/full-edit flow in `frontend/src/modules/posts/QuickCaptureDialog.vue`
- [ ] T045 [US1] Integrate capture dialogs, default options, source status notifications and redirects into `frontend/src/modules/posts/PostListPage.vue` and `frontend/src/modules/posts/BlogModuleLayout.vue`

**Checkpoint**: US1 independently delivers reliable capture even when all intelligence and background processing are unavailable.

---

## Phase 4: User Story 2 — 编辑并组织正式文章 (Priority: P1) 🎯 MVP-2

**Goal**: Edit canonical Markdown through rich/source/split modes, auto-save complete versions and manage content type, taxonomy and dynamic fields without data loss.

**Independent Test**: Round-trip a technical article containing headings, table, quote, code, command, link and image through both modes; change content types twice; reload and verify current plus hidden structured fields.

### Tests for User Story 2 — write first ⚠️

- [ ] T046 [P] [US2] Add Post patch, content-type and source-summary contract tests in `backend/tests/contract/test_blog_content_api.py`
- [ ] T047 [P] [US2] Add full-field snapshot, hidden dynamic field and concurrent autosave integration tests in `backend/tests/integration/test_blog_editor_versions.py`
- [ ] T048 [P] [US2] Add supported Markdown round-trip fixtures for rich/source conversion in `frontend/tests/unit/blog-markdown-roundtrip.spec.ts`
- [ ] T049 [P] [US2] Add editor modes, save states, conversion warning and property-sidebar component tests in `frontend/tests/component/blog-editor.spec.ts`
- [ ] T050 [P] [US2] Add keyboard, focus, narrow viewport and article-edit E2E coverage in `frontend/tests/e2e/blog-content-management.spec.ts`

### Implementation for User Story 2

- [ ] T051 [US2] Extend Post save validation for all common/dynamic fields, owned taxonomy relations, status transitions and search Outbox in `backend/app/modules/posts/service.py`
- [ ] T052 [US2] Implement content-type list/create/update endpoints and schema-version warnings in `backend/app/modules/posts/query_router.py` and `backend/app/modules/posts/content_types.py`
- [ ] T053 [US2] Extend private Post GET/PATCH serialization with sources, AI summary, organization fields and strict optimistic version in `backend/app/modules/posts/router.py`
- [ ] T054 [P] [US2] Implement typed current Post, content-type and revision API clients in `frontend/src/api/posts.ts` and `frontend/src/api/blogQueries.ts`
- [ ] T055 [P] [US2] Implement canonical source-mode editor with cursor retention and local unsaved buffer in `frontend/src/modules/posts/MarkdownSourceEditor.vue`
- [ ] T056 [P] [US2] Implement Milkdown rich editor with the MVP supported-block matrix and Markdown update listener in `frontend/src/modules/posts/RichMarkdownEditor.vue`
- [ ] T057 [P] [US2] Implement sanitized Markdown preview, code copy/highlight, Mermaid and formula read-only rendering in `frontend/src/modules/posts/MarkdownPreview.vue`
- [ ] T058 [P] [US2] Implement class/type/category/tag/keyword/source/status/time/Skill/version property controls in `frontend/src/modules/posts/PostPropertySidebar.vue`
- [ ] T059 [US2] Rebuild the editor shell with mode switching, split/fullscreen/focus modes, outline and conversion-risk confirmation in `frontend/src/modules/posts/PostEditorPage.vue`
- [ ] T060 [US2] Implement debounced autosave, explicit save, navigation guard, conflict reload and visible save state in `frontend/src/modules/posts/usePostAutosave.ts`
- [ ] T061 [US2] Implement read-only article rendering with separate source and user-content regions in `frontend/src/modules/posts/PostViewPage.vue`

**Checkpoint**: US2 is a complete non-AI writing and organization tool built on durable versions.

---

## Phase 5: User Story 3 — 异步执行 AI 优化 (Priority: P1) 🎯 MVP-3

**Goal**: Submit fixed-version AI work, expose durable business stages, validate structured output and save only candidate results without blocking editing.

**Independent Test**: Submit full optimization, continue editing elsewhere, follow Job stages, and produce valid, malformed, timed-out and protected-token-changing outputs; only valid/partial candidates persist.

### Tests for User Story 3 — write first ⚠️

- [ ] T062 [P] [US3] Add optimize endpoint, fixed binding and blog Job response contract tests in `backend/tests/contract/test_blog_content_api.py`
- [ ] T063 [P] [US3] Add JSON Schema/Pydantic drift and malformed output tests in `backend/tests/contract/test_blog_ai_schema.py`
- [ ] T064 [P] [US3] Add Skill resolution, duplicate request and stage transition integration tests in `backend/tests/integration/test_blog_ai_pipeline.py`
- [ ] T065 [P] [US3] Add code/command/URL/number/date/quote extraction and comparison tests in `backend/tests/unit/test_blog_protected_tokens.py`
- [ ] T066 [P] [US3] Add field safety ceiling and full/partial/rejected validation tests in `backend/tests/unit/test_blog_field_policy.py`
- [ ] T067 [P] [US3] Add provider timeout, broker outage, cancellation, redelivery and candidate-save crash tests in `backend/tests/reliability/test_blog_failure_matrix.py`
- [ ] T068 [P] [US3] Add optimize panel, inline status and blog Job list/detail component tests in `frontend/tests/component/blog-ai-candidate.spec.ts`

### Implementation for User Story 3

- [ ] T069 [P] [US3] Implement protected token extraction, hash comparison and blocking/warning classification in `backend/app/modules/posts/protected_content.py`
- [ ] T070 [P] [US3] Implement effective field policy calculation and top-level/dynamic path validation in `backend/app/modules/posts/field_policy.py`
- [ ] T071 [US3] Implement AI run submission, exact-duplicate detection, fixed Skill/model/schema binding and Outbox transaction in `backend/app/modules/posts/ai_service.py`
- [ ] T072 [US3] Implement optimize, run detail and allowed cancel/retry endpoints in `backend/app/modules/posts/ai_router.py`
- [ ] T073 [US3] Implement preprocessing, content recognition, long-content strategy, structured model call and deterministic result validation in `backend/app/workers/tasks/blog.py`
- [ ] T074 [US3] Implement atomic AI revision/candidate save, complete/partial outcome and waiting-user Job events in `backend/app/workers/tasks/blog.py`
- [ ] T075 [US3] Extend Job filters, retry dispatch, cancellation checkpoints and blog-safe result summaries in `backend/app/modules/jobs/router.py` and `backend/app/modules/jobs/service.py`
- [ ] T076 [US3] Add completion/failure notifications with links and no article content in `backend/app/modules/notifications/service.py` and `backend/app/workers/tasks/blog.py`
- [ ] T077 [P] [US3] Implement optimize/run/candidate API types and clients in `frontend/src/api/blogAI.ts`
- [ ] T078 [P] [US3] Implement optimization type/scope/Skill/model advanced panel in `frontend/src/modules/posts/OptimizePostDialog.vue`
- [ ] T079 [US3] Implement blog Job list/detail pages and SSE-backed article status summaries in `frontend/src/modules/posts/BlogJobsPage.vue`, `frontend/src/modules/posts/BlogJobDetailPage.vue`, and `frontend/src/stores/jobs.ts`

**Checkpoint**: US3 creates observable candidates and never mutates current article content.

---

## Phase 6: User Story 4 — 审核并按字段应用 AI 结果 (Priority: P1) 🎯 MVP-4

**Goal**: Compare base/current/candidate snapshots and apply only selected safe fields through a fresh version-checked revision.

**Independent Test**: Generate from V1, edit to V2, receive a multi-field candidate, apply only summary and tags, and verify V2 body remains unchanged while V3 records the decision.

### Tests for User Story 4 — write first ⚠️

- [ ] T080 [P] [US4] Add candidate list/detail/decision and version compare contract tests in `backend/tests/contract/test_blog_content_api.py`
- [ ] T081 [P] [US4] Add unchanged auto-fill, changed forced-merge and selected-field apply integration tests in `backend/tests/integration/test_blog_candidate_merge.py`
- [ ] T082 [P] [US4] Add apply-versus-save race, duplicate decision and stale candidate reliability tests in `backend/tests/reliability/test_blog_failure_matrix.py`
- [ ] T083 [P] [US4] Add cross-user candidate/revision/decision isolation tests in `backend/tests/security/test_blog_url_and_ownership.py`
- [ ] T084 [P] [US4] Add three-way body/field diff, risk filter and selected-field component tests in `frontend/tests/component/blog-ai-candidate.spec.ts`
- [ ] T085 [P] [US4] Add summary-and-tags-only application E2E coverage in `frontend/tests/e2e/blog-content-management.spec.ts`

### Implementation for User Story 4

- [ ] T086 [P] [US4] Implement stable body diff and typed field diff generation for arbitrary revision pairs in `backend/app/modules/posts/diffing.py`
- [ ] T087 [US4] Implement candidate conflict derivation, three-way comparison and validation summaries in `backend/app/modules/posts/ai_service.py`
- [ ] T088 [US4] Implement transactional candidate decision locking, version recheck, selected-field merge and new revision creation in `backend/app/modules/posts/ai_service.py`
- [ ] T089 [US4] Implement candidate list/detail/decide plus version list/detail/compare/restore endpoints in `backend/app/modules/posts/ai_router.py` and `backend/app/modules/posts/router.py`
- [ ] T090 [US4] Record candidate selections, rejects, copies, applied revision and safe Activity summaries in `backend/app/modules/posts/ai_service.py`
- [ ] T091 [P] [US4] Extend candidate comparison and decision API clients in `frontend/src/api/blogAI.ts` and `frontend/src/api/posts.ts`
- [ ] T092 [P] [US4] Upgrade reusable body diff rendering for base/current/candidate modes in `frontend/src/modules/posts/RevisionDiff.vue`
- [ ] T093 [US4] Implement risk-first three-way compare, field selection and final impact confirmation in `frontend/src/modules/posts/CandidateComparePage.vue`
- [ ] T094 [P] [US4] Implement version timeline, two-version compare, restore and create-copy controls in `frontend/src/modules/posts/PostVersionsPage.vue`
- [ ] T095 [US4] Add pending-review/merge badges and navigation from editor, view, list and Job pages in `frontend/src/modules/posts/PostEditorPage.vue`, `frontend/src/modules/posts/PostViewPage.vue`, and `frontend/src/modules/posts/PostListPage.vue`
- [ ] T096 [US4] Verify every candidate terminal action leaves immutable candidate/run/version history in `backend/tests/integration/test_blog_candidate_merge.py`

**Checkpoint**: US4 completes the safe AI review loop with reversible, field-level application.

---

## Phase 7: User Story 5 — 配置并版本化 Skill (Priority: P1) 🎯 MVP-5

**Goal**: Manage structured blog Skills, immutable versions and deterministic defaults while historical runs remain reproducible.

**Independent Test**: Submit T1 with Skill v1, edit to v2, run T1 and submit T2; verify old/new bindings. Restore v1 and confirm a new v3.

### Tests for User Story 5 — write first ⚠️

- [ ] T097 [P] [US5] Add Skill CRUD/version/restore/default API contract tests in `backend/tests/contract/test_blog_content_api.py`
- [ ] T098 [P] [US5] Add manual/type/class/global matching and disabled/incomplete fallback unit tests in `backend/tests/unit/test_blog_skill_matching.py`
- [ ] T099 [P] [US5] Add immutable history, queued old-version and unique-default integration tests in `backend/tests/integration/test_blog_skills.py`
- [ ] T100 [P] [US5] Add cross-user Skill/default/version isolation tests in `backend/tests/security/test_blog_url_and_ownership.py`
- [ ] T101 [P] [US5] Add Skill list/editor/version/default component tests in `frontend/tests/component/blog-skills.spec.ts`

### Implementation for User Story 5

- [ ] T102 [US5] Implement Skill create/edit-as-new-version/copy/enable/disable/restore and recent-execution queries in `backend/app/modules/posts/skill_service.py`
- [ ] T103 [US5] Implement unique default replacement and impacted-scope validation in `backend/app/modules/posts/skill_service.py`
- [ ] T104 [US5] Implement Skill list/detail/write/version/restore/default endpoints in `backend/app/modules/posts/skill_router.py`
- [ ] T105 [P] [US5] Implement typed Skill/default/version API client in `frontend/src/api/blogSkills.ts`
- [ ] T106 [P] [US5] Implement searchable Skill list, state/default badges and safe enable/disable confirmation in `frontend/src/modules/posts/SkillListPage.vue`
- [ ] T107 [US5] Implement sectioned Skill editor with field policy table, safety-ceiling errors and impact summary in `frontend/src/modules/posts/SkillEditorPage.vue`
- [ ] T108 [P] [US5] Implement immutable Skill timeline, pair comparison and restore-as-new-version in `frontend/src/modules/posts/SkillVersionsPage.vue`
- [ ] T109 [US5] Wire current Skill and matching explanation into create/optimize/property panels in `frontend/src/modules/posts/PostCreateDialog.vue`, `frontend/src/modules/posts/OptimizePostDialog.vue`, and `frontend/src/modules/posts/PostPropertySidebar.vue`
- [ ] T110 [US5] Seed initial safe global/class Skills without replacing user-defined Skills in `backend/app/modules/posts/content_types.py` and `backend/alembic/versions/0011_blog_content_management.py`
- [ ] T111 [US5] Verify historical PostAIRun and candidate detail continue resolving deleted/disabled SkillVersion data in `backend/tests/integration/test_blog_skills.py`

**Checkpoint**: US5 makes AI behavior configurable and reproducible without becoming a standalone model platform.

---

## Phase 8: User Story 6 — 管理文章与待整理内容 (Priority: P1) 🎯 MVP-6

**Goal**: Filter and manage articles/triage, perform safe batch operations and merge ordered records without losing sources.

**Independent Test**: Create four triage reasons, filter them, bulk assign class/Skill with one injected failure, then merge two in order and retain both originals.

### Tests for User Story 6 — write first ⚠️

- [ ] T112 [P] [US6] Add Post list filters, triage derivation, batch result and merge API contract tests in `backend/tests/contract/test_blog_content_api.py`
- [ ] T113 [P] [US6] Add quick/failed/stale/draft triage and ordered source merge integration tests in `backend/tests/integration/test_blog_management.py`
- [ ] T114 [P] [US6] Add archive/discard/delete/public-compatibility and batch partial-failure reliability tests in `backend/tests/reliability/test_blog_failure_matrix.py`
- [ ] T115 [P] [US6] Add article list/filter/batch and triage/merge component tests in `frontend/tests/component/blog-management.spec.ts`

### Implementation for User Story 6

- [ ] T116 [US6] Implement cursor Post listing, filters, counts, sort and derived AI/source summaries in `backend/app/modules/posts/query_service.py`
- [ ] T117 [US6] Implement triage reason query, stale threshold and quick preview projections in `backend/app/modules/posts/query_service.py`
- [ ] T118 [US6] Implement transactional ordered merge, source relations and optional source status update in `backend/app/modules/posts/service.py`
- [ ] T119 [US6] Implement itemized batch class/Skill/tag/category/status/AI operations with no whole-batch rollback in `backend/app/modules/posts/service.py`
- [ ] T120 [US6] Implement article list, triage, merge, batch, archive and export endpoints in `backend/app/modules/posts/query_router.py`
- [ ] T121 [P] [US6] Extend typed list/triage/batch/merge clients in `frontend/src/api/blogQueries.ts`
- [ ] T122 [US6] Rebuild Post list with search, combination filters, AI/source states, pagination and selection toolbar in `frontend/src/modules/posts/PostListPage.vue`
- [ ] T123 [P] [US6] Implement triage list, reason filters, quick preview and item actions in `frontend/src/modules/posts/TriagePage.vue`
- [ ] T124 [P] [US6] Implement ordered merge preview, title and source completion choices in `frontend/src/modules/posts/TriageMergeDialog.vue`
- [ ] T125 [US6] Implement per-item batch progress and partial failure feedback in `frontend/src/modules/posts/PostBatchActionBar.vue`
- [ ] T126 [US6] Add archive/discard/delete confirmations that preserve public compatibility and recoverable state in `frontend/src/modules/posts/PostViewPage.vue` and `frontend/src/modules/posts/PostListPage.vue`

**Checkpoint**: US6 completes the MVP operational loop from capture backlog to organized articles.

---

## Phase 9: User Story 7 — 搜索和回顾长期内容 (Priority: P2)

**Goal**: Search deep blog fields immediately and through the global search, then review articles by occurrence or creation timeline.

**Independent Test**: Search unique markers in title/body/code/source/structured fields before and after index refresh, then find one year's technical incident records in the timeline.

### Tests for User Story 7 — write first ⚠️

- [ ] T127 [P] [US7] Add module search/timeline query and response contract tests in `backend/tests/contract/test_blog_content_api.py`
- [ ] T128 [P] [US7] Add direct-data, derived-index, combined-filter, CJK/code and time fallback integration tests in `backend/tests/integration/test_blog_search_timeline.py`
- [ ] T129 [P] [US7] Extend global search ownership and Post deep-field tests in `backend/tests/integration/test_search.py`
- [ ] T130 [P] [US7] Add 100,000-Post search p95 and timeline cursor stability tests in `backend/tests/performance/test_blog_search_100k.py`
- [ ] T131 [P] [US7] Add search filter/highlight and timeline expansion component tests in `frontend/tests/component/blog-discovery.spec.ts`

### Implementation for User Story 7

- [ ] T132 [US7] Implement owned module search across current Post, source URL, taxonomy, code and flattened structured fields in `backend/app/modules/posts/query_service.py`
- [ ] T133 [US7] Extend direct global Post search with summary/body/taxonomy/structured matches and safe highlights in `backend/app/modules/search/service.py`
- [ ] T134 [US7] Extend idempotent Post SearchDocument refresh with body, summary, tags, category, keywords and metadata in `backend/app/workers/tasks/search.py`
- [ ] T135 [US7] Implement occurrence/creation timeline cursor queries and explicit fallback basis in `backend/app/modules/posts/query_service.py`
- [ ] T136 [US7] Implement module search and timeline endpoints in `backend/app/modules/posts/query_router.py`
- [ ] T137 [US7] Add or tune Post/title/body/JSONB/taxonomy indexes only from measured plans in `backend/alembic/versions/0011_blog_content_management.py`
- [ ] T138 [P] [US7] Implement typed search/timeline clients and filter serialization in `frontend/src/api/blogQueries.ts`
- [ ] T139 [US7] Add module deep-search bar, filter chips, match fields and safe highlights to `frontend/src/modules/posts/PostListPage.vue`
- [ ] T140 [US7] Implement year/month grouping, time-basis switch, filters and stable cursor loading in `frontend/src/modules/posts/TimelinePage.vue`
- [ ] T141 [US7] Route global `post` results into view/edit pages with preserved query context in `frontend/src/modules/search/SearchResults.vue` and `frontend/src/router/index.ts`

**Checkpoint**: US7 makes every committed article findable without waiting for a derived index and provides basic long-term time review.

---

## Phase 10: User Story 8 — 维护分类、标签和关键词 (Priority: P2)

**Goal**: Govern separate category, tag and keyword concepts with aliases, hierarchy, stop words, merges and historical visibility.

**Independent Test**: Create a category tree, tag alias and keyword synonym; reject a cycle; merge duplicate tags; disable a category and verify old/new behavior.

### Tests for User Story 8 — write first ⚠️

- [ ] T142 [P] [US8] Add category/tag/keyword CRUD, alias, merge and recompute contract tests in `backend/tests/contract/test_blog_content_api.py`
- [ ] T143 [P] [US8] Add cycle, uniqueness, ownership, disabled history and atomic merge integration tests in `backend/tests/integration/test_blog_taxonomy.py`
- [ ] T144 [P] [US8] Add duplicate merge redelivery and large recompute recovery tests in `backend/tests/reliability/test_blog_failure_matrix.py`
- [ ] T145 [P] [US8] Add three-tab taxonomy, merge-impact and disabled-state component tests in `frontend/tests/component/blog-management.spec.ts`

### Implementation for User Story 8

- [ ] T146 [US8] Implement category tree validation, bounded depth, sorting, enable/disable and counts in `backend/app/modules/posts/taxonomy_service.py`
- [ ] T147 [US8] Implement tag profile, alias resolution, collision checks, AI recommendation normalization and counts in `backend/app/modules/posts/taxonomy_service.py`
- [ ] T148 [US8] Implement keyword, synonym, stop-word, manual/AI/recomputed link and count rules in `backend/app/modules/posts/taxonomy_service.py`
- [ ] T149 [US8] Implement transactional small merge and idempotent background large merge with TaxonomyMerge audit in `backend/app/modules/posts/taxonomy_service.py` and `backend/app/workers/tasks/blog.py`
- [ ] T150 [US8] Implement taxonomy list/create/update/merge and keyword recompute endpoints in `backend/app/modules/posts/taxonomy_router.py`
- [ ] T151 [P] [US8] Implement typed taxonomy and merge API client in `frontend/src/api/blogTaxonomy.ts`
- [ ] T152 [US8] Implement separate category tree, tag and keyword tabs with concept guidance in `frontend/src/modules/posts/TaxonomyPage.vue`
- [ ] T153 [P] [US8] Implement taxonomy edit drawers for hierarchy, alias, color, description, stop-word and enabled fields in `frontend/src/modules/posts/TaxonomyEditDrawer.vue`
- [ ] T154 [P] [US8] Implement merge impact preview, target selection and asynchronous result states in `frontend/src/modules/posts/TaxonomyMergeDialog.vue`
- [ ] T155 [US8] Update article property controls to resolve aliases and exclude disabled choices without hiding history in `frontend/src/modules/posts/PostPropertySidebar.vue`

**Checkpoint**: US8 keeps classification, browsing attributes and search terms distinct and maintainable.

---

## Phase 11: User Story 9 — 用词云辅助发现内容 (Priority: P3)

**Goal**: Generate durable, filter-specific tag or keyword word clouds that degrade to the last valid snapshot and link back to article filters.

**Independent Test**: Build one year's keyword cloud, enforce stop words/frequency/limit, click a canonical term, then fail a rebuild and retain the previous result.

### Tests for User Story 9 — write first ⚠️

- [ ] T156 [P] [US9] Add word-cloud get/rebuild contract tests in `backend/tests/contract/test_blog_content_api.py`
- [ ] T157 [P] [US9] Add filter hash, stop-word, threshold, max-term and last-success fallback integration tests in `backend/tests/integration/test_blog_word_cloud.py`
- [ ] T158 [P] [US9] Add duplicate rebuild, cancellation and failure-preserves-snapshot reliability tests in `backend/tests/reliability/test_blog_failure_matrix.py`
- [ ] T159 [P] [US9] Add cloud controls, loading/stale/empty states and term-navigation component tests in `frontend/tests/component/blog-discovery.spec.ts`

### Implementation for User Story 9

- [ ] T160 [US9] Implement canonical filter normalization/hash, last-success lookup and rebuild Job transaction in `backend/app/modules/posts/query_service.py`
- [ ] T161 [US9] Implement idempotent tag/keyword aggregation, stop-word/threshold/limit application and snapshot replacement in `backend/app/workers/tasks/blog.py`
- [ ] T162 [US9] Implement word-cloud get/rebuild endpoints and business error serialization in `backend/app/modules/posts/query_router.py`
- [ ] T163 [P] [US9] Implement typed word-cloud client in `frontend/src/api/blogQueries.ts`
- [ ] T164 [US9] Implement source switch, time/class/category filters, controls, last-updated and stale/error display in `frontend/src/modules/posts/WordCloudPage.vue`
- [ ] T165 [US9] Implement accessible bounded-size cloud layout with non-color frequency cues in `frontend/src/modules/posts/WordCloudView.vue`
- [ ] T166 [US9] Link canonical tag/keyword clicks to clearable Post list filters in `frontend/src/modules/posts/WordCloudPage.vue` and `frontend/src/modules/posts/PostListPage.vue`
- [ ] T167 [US9] Add word-cloud settings fields and explicit on-demand rebuild behavior in `frontend/src/modules/posts/BlogSettingsPage.vue`

**Checkpoint**: US9 remains a derived exploration aid and never becomes a dependency for search or article saves.

---

## Phase 12: Polish & Cross-Cutting Concerns

**Purpose**: Complete settings, accessibility, observability, schema drift, performance and full regression after all selected story phases.

- [ ] T168 [P] Implement complete create/clipboard/URL/AI/word-cloud settings API and Activity logging in `backend/app/modules/posts/settings_router.py` and `backend/app/modules/posts/settings_service.py`
- [ ] T169 [P] Implement grouped settings UI, restore-group-default and high-risk impact summaries in `frontend/src/modules/posts/BlogSettingsPage.vue` and `frontend/src/api/blogSettings.ts`
- [ ] T170 [P] Add Skill dry-run Job and result validation without Post mutation in `backend/app/modules/posts/skill_router.py`, `backend/app/workers/tasks/blog.py`, and `frontend/src/modules/posts/SkillTestPage.vue`
- [ ] T171 Add safe trace/job/post/source/skill logging, metrics and content-redaction assertions in `backend/app/core/observability.py` and `backend/tests/security/test_blog_logging.py`
- [ ] T172 Add keyboard, focus, screen-reader, status-not-color-only and 360px acceptance coverage in `frontend/tests/e2e/accessibility.spec.ts` and `frontend/tests/e2e/blog-content-management.spec.ts`
- [ ] T173 Execute all 17 required acceptance cases and fill evidence references in `specs/005-blog-content-management/quickstart.md`
- [ ] T174 Validate OpenAPI/AsyncAPI/AI/Skill schema drift against implementations in `backend/tests/contract/test_blog_content_contracts.py` and `backend/tests/contract/test_blog_ai_schema.py`
- [ ] T175 Validate migration upgrade on existing Posts data, application rollback retention and public/RSS compatibility in `backend/tests/integration/test_blog_content_migration.py` and `backend/tests/contract/test_posts_api.py`
- [ ] T176 Run 100,000-Post search, timeline and word-cloud budgets and document measured index decisions in `backend/tests/performance/test_blog_search_100k.py` and `specs/005-blog-content-management/quickstart.md`
- [ ] T177 Run full backend lint/type/test suites and fix feature regressions in `backend/app/modules/posts/` and `backend/tests/`
- [ ] T178 Run full frontend lint/type/component/E2E/build suites and fix feature regressions in `frontend/src/modules/posts/` and `frontend/tests/`
- [ ] T179 Verify Compose startup, migration, health, Outbox recovery, Worker routing and one capture-to-AI-to-apply happy path in `compose.yaml` and `specs/005-blog-content-management/quickstart.md`

---

## Dependencies & Execution Order

### Phase dependencies

```text
Phase 1 Setup
  → Phase 2 Foundation (blocks every story)
    → US1 Reliable capture ─┐
    → US2 Editor           ├→ US6 Management
    → US3 Async AI → US4 Review
    → US5 Skills ──────────┘
    → US7 Search/Timeline (uses current Post projection from US2)
    → US8 Taxonomy (can begin after Foundation; integrates with US2/US6/US7)
    → US9 Word Cloud (requires US7 queries + US8 canonical terms)
      → Phase 12 Polish for all selected stories
```

### User-story dependencies

- **US1 (P1)**: Foundation only. Delivers independent durable capture; AI toggle may remain queued until US3.
- **US2 (P1)**: Foundation only. Delivers independent non-AI writing, complete versions and organization fields.
- **US3 (P1)**: Foundation and base Skill matching from T022. Produces candidates; it does not require the Skill management UI.
- **US4 (P1)**: Requires US3 candidate production and US2 current-version editing.
- **US5 (P1)**: Foundation only for CRUD/versioning; its default controls improve US1/US3 but remain independently testable.
- **US6 (P1)**: Requires US1 sources and US2 Post projection; batch AI additionally uses US3/US5 when present.
- **US7 (P2)**: Requires US2 current projection and search Outbox; it can ship without US8 advanced governance.
- **US8 (P2)**: Foundation only for taxonomy governance; integration tasks update US2/US6/US7 behavior.
- **US9 (P3)**: Requires US7 query filters and US8 canonical tags/keywords.

### Within each story

1. Write contract/unit/integration/security/reliability/component/E2E tests and confirm the relevant new assertions fail.
2. Implement domain rules and persistence before routers/Workers.
3. Implement API contracts before frontend clients.
4. Implement frontend components before the story E2E checkpoint.
5. Run the story's independent test plus all earlier completed-story regression suites.

## Parallel Opportunities

- Setup tasks T002–T005 can proceed in parallel after T001 dependency resolution is understood.
- Foundation tests T007–T011 can proceed in parallel; model groups T014–T015 can be drafted in parallel before T016 integrates them.
- After Foundation, US1, US2, US5 and the backend portion of US8 may proceed in parallel on different submodules.
- Within each story, tasks marked `[P]` touch distinct test or component files and can be assigned independently.
- US3 protected-content/policy work (T069–T070) can proceed in parallel before AI orchestration integration.
- US4 backend diffing (T086) and frontend reusable revision display (T092) can proceed in parallel.
- US7 global search, Post index refresh and frontend typed client tasks can proceed in parallel after query shapes are fixed.
- Polish backend settings, frontend settings, Skill dry-run and accessibility tasks can proceed in parallel before final regression.

## Parallel Examples

### Example A — MVP capture and editor after Foundation

```text
Track A: T028–T045 (US1 capture)
Track B: T046–T061 (US2 editor)
Track C: T097–T111 (US5 Skill management)
```

These tracks share foundational models but primarily change separate service and component files. Coordinate only the central `router.py`, `models/blog.py` and route registration edits.

### Example B — AI validation before orchestration

```text
T063: AI schema drift tests
T065: protected-token tests
T066: field-policy tests
T069: protected-content implementation
T070: field-policy implementation
```

After these complete, T071–T074 integrate durable run submission and candidate creation.

### Example C — Discovery features

```text
T133: global search extension
T134: derived Post index refresh
T138: frontend query client
T146–T148: taxonomy rule services
```

US9 starts only after US7 and US8 checkpoints because its filter identity depends on both.

## Implementation Strategy

### Smallest deployable increment

1. Complete Setup and Foundation.
2. Complete US1 to guarantee reliable multi-source capture.
3. Complete US2 to make captured content manually editable and versioned.
4. Stop and validate both independently. This is the smallest useful non-AI blog-content increment.

### Requested MVP closure

Add in this order:

1. US3 asynchronous AI candidate generation.
2. US4 three-way, field-level review.
3. US5 configurable/versioned Skills.
4. US6 article and triage management.
5. US7 basic search and timeline.

This yields the specification's capture → organize → AI candidate → safe apply → manage → retrieve loop. US8 governance can follow immediately; US9 word cloud remains P3.

### Incremental delivery checkpoints

- **Checkpoint 1**: US1 — content never depends on AI/Worker availability.
- **Checkpoint 2**: US2 — durable manual blog and full history.
- **Checkpoint 3**: US3 + US4 — safe asynchronous AI loop.
- **Checkpoint 4**: US5 + US6 — configurable rules and manageable backlog.
- **Checkpoint 5**: US7 + US8 — long-term retrieval and taxonomy governance.
- **Checkpoint 6**: US9 — optional exploration.

## Task Coverage Notes

- Durable save, AI authority, fixed Skill versions, field policies, protected content, ownership, Outbox/idempotency, observable Jobs and failure recovery are represented in Foundation and repeated in story-specific tests.
- Existing public publishing is regression-tested but not expanded.
- Template/file import, full Skill import/export analytics and advanced editor blocks remain P1 follow-up work unless explicitly added to this feature scope later.
- No task creates a new user/role system, media center, model platform, search service, Worker process, public blog site, knowledge graph, map, multi-Agent workflow or auto-publisher.
