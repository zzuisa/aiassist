# Quickstart and Acceptance Guide: 博客内容管理扩展

**Feature**: `005-blog-content-management`  
**Branch**: `005-blog-content-management`

本指南用于实现期间的独立故事验收和最终回归。它不替代部署文档；启动、迁移、登录、对象存储、模型和消息依赖均复用总站现有流程。

## 1. Prerequisites

1. 当前分支为 `005-blog-content-management`。
2. PostgreSQL、Redis、RabbitMQ、对象存储适配器、后端、两个 Worker、Outbox publisher 和前端按现有 Compose 启动。
3. 已执行迁移到 `0011_blog_content_management`。
4. 建立两个用户：`owner` 与 `other`，用于所有权矩阵。
5. 为 owner 创建：
   - 技术大类默认 Skill `S-tech-v1`；
   - 故障复盘内容类型默认 Skill `S-incident-v1`；
   - 一个备用手动 Skill `S-manual-v1`；
   - 分类 `技术/Linux`、标签 `Kubernetes`、关键词 `CrashLoopBackOff`。
6. 测试模型使用现有 FakeProvider 或隔离的测试 Provider，能够返回指定 `blog-optimization.v1` JSON。
7. URL 抓取使用可控 HTTP 测试站点与伪 DNS，不访问真实私有网络。

## 2. Contract and Migration Gate

Run before user-story work:

```bash
cd backend
pytest tests/contract/test_blog_content_api.py \
  tests/contract/test_blog_async_contracts.py \
  tests/contract/test_blog_ai_schema.py
alembic upgrade head
alembic downgrade 0010
alembic upgrade head
```

Then verify existing Post publishing and RSS contract tests still pass. Downgrade is only for empty/test databases because new complete snapshots cannot be represented by the old schema.

## 3. User Story Independent Tests

### US1 — Reliable capture before processing

1. Disable the AI provider and stop heavy Worker consumption.
2. Create a plain-text clipboard post.
3. Confirm the response includes Post, PostSource and current revision; no AI completion is required.
4. Create a URL note while the test HTTP endpoint times out.
5. Confirm the URL, user note, Post and source remain visible in triage with a retryable business error.
6. Restart processing and retry; ensure exactly one extracted result becomes available.

**Pass**: accepted original content survives every provider/queue failure and can be edited immediately.

### US2 — Editor and structured organization

1. Create Markdown with headings, table, quote, fenced Python, shell command, link and image reference.
2. Open rich mode, edit a paragraph, switch to Markdown and split preview.
3. Save, reload and compare semantic structure and protected tokens.
4. Change type to incident review, fill dynamic fields, then switch type away and back.
5. Trigger a second-client version conflict.

**Pass**: supported content round-trips, historical dynamic values remain, and concurrent saves never silently overwrite.

### US3 — Asynchronous AI optimization

1. Save an unstructured technical note and submit full optimization.
2. Confirm the response is `202`, the Post remains editable and the Job binds base revision and Skill version.
3. Observe stages through the existing Job SSE stream.
4. Return valid schema output, malformed output, timeout and protected-token mutation in separate runs.

**Pass**: every run reaches a durable, understandable terminal/waiting state; only validated candidates are saved.

### US4 — Candidate review and field-level application

1. Submit AI from revision V1.
2. While processing, save user revision V2.
3. Return a candidate changing body, summary and tags.
4. Confirm status is `merge_required` and comparison returns V1, V2 and candidate.
5. Apply only summary and tags using V2's current Post version.
6. Verify body equals V2 and a new `ai_applied` revision V3 exists.
7. Race a user save against candidate decision and verify one side returns version conflict without losing either snapshot.

**Pass**: no background or stale decision overwrites user content; every selected field is traceable.

### US5 — Versioned Skill behavior

1. Resolve Skill for a technical incident with no manual selection; expect incident type default.
2. Submit task T1 bound to `S-incident-v1`.
3. Modify the Skill and save immutable `v2`.
4. Execute T1 and create T2.
5. Verify T1 uses v1 and T2 uses v2.
6. Submit with `S-manual-v1`; verify it overrides defaults without changing them.
7. Restore v1 and verify a new v3 is created.

**Pass**: history is immutable and resolution order is deterministic.

### US6 — Articles and triage management

1. Create a quick record, failed URL source, clipboard fragment and unfinished draft.
2. Filter triage by source and content class.
3. Bulk assign class/Skill and submit per-item AI jobs; inject one failure.
4. Merge two records in an explicit order.

**Pass**: the merged Post contains both source relationships, original records are not deleted by default, and partial batch failure is itemized.

### US7 — Search and timeline

1. Create posts whose title, Markdown, code, source URL and structured fields contain distinct markers.
2. Search immediately before the derived search worker runs.
3. Run index refresh and repeat combined class/type/tag/time filters.
4. Set occurrence dates in different years and query the technical incident timeline.
5. Search from the总站 global search page and open a Post.

**Pass**: committed content is always findable, results respect ownership, and timeline clearly reports occurrence/creation fallback.

### US8 — Category, tag and keyword governance

1. Create a category tree, tag with alias, keyword with synonym and a stop word.
2. Attempt a category cycle and cross-user target; both must fail.
3. Merge two tags and verify Post links and counts move atomically.
4. Disable a category and confirm historical Posts display it while new selection excludes it.

**Pass**: three concepts remain distinct and merges preserve current relationships plus audit mapping.

### US9 — Word-cloud exploration

1. Prepare posts across two years with tags/keywords and configured stop words.
2. Request a keyword snapshot for one year and wait for the durable Job.
3. Verify min frequency, max terms and stop-word exclusion.
4. Click a term and confirm the Post list receives the canonical keyword filter.
5. Force rebuild failure and verify the last successful snapshot still renders with stale/error indication.

**Pass**: word cloud is an optional derived view and never affects search or article access.

## 4. Required Acceptance Matrix

| # | Scenario | Primary automated coverage | Required assertion |
|---|---|---|---|
| 1 | Plain-text clipboard | contract + integration + component | Raw source and draft saved before AI |
| 2 | Rich clipboard with code | normalization unit + component | Structure retained, code unchanged |
| 3 | Single URL note | contract + integration | URL metadata and draft created |
| 4 | URL extraction failure | reliability | Source remains, triage + retry available |
| 5 | Create with AI enabled | integration | Job created only after revision commit |
| 6 | Class default Skill | unit + integration | Correct fixed Skill version |
| 7 | Manual Skill override | unit + integration | Manual wins without changing defaults |
| 8 | Full structured fill | AI schema + integration | All candidate fields independently reviewable |
| 9 | Fill empty only | field-policy unit | Existing user value unchanged |
| 10 | Edit during AI | concurrency integration | Current revision preserved |
| 11 | Candidate needs merge | integration + component | Three versions available |
| 12 | Apply tags and summary only | integration + E2E | Body byte-for-byte unchanged |
| 13 | Skill edit version | integration | New immutable version created |
| 14 | Historical task old Skill | integration | Old binding remains |
| 15 | AI failure retry | reliability | Article survives; retry is new tracked attempt |
| 16 | Timeline yearly incident | integration + E2E | Correct filtered items and time basis |
| 17 | Word-cloud term click | component + E2E | Canonical Post filter applied |

## 5. Security and Reliability Matrix

### URL safety

- Reject `file:`, `ftp:`, `gopher:`, `data:` and URL credentials.
- Reject loopback/private/link-local/reserved/multicast IPv4 and IPv6.
- Reject public-to-private redirects and DNS answers containing forbidden addresses.
- Revalidate every redirect, cap redirects, time, media type and streamed bytes.
- Never forward session cookies, CSRF tokens, Authorization, proxy credentials or internal headers.

### Ownership

For every Post, Source, Revision, Candidate, Run, Skill, SkillVersion, taxonomy item, settings, word-cloud snapshot and protected asset endpoint:

1. Owner succeeds.
2. Other authenticated user receives indistinguishable not-found behavior.
3. Anonymous request is rejected.
4. Cross-user IDs in a valid owner request are rejected without creating partial relationships.

### Idempotency and failure

- Deliver each async command ten times; one source extraction/candidate/search document/snapshot results.
- Stop broker after business commit; Outbox reconcile eventually dispatches.
- Crash Worker after model response but before commit; retry creates at most one candidate.
- Cancel before model call and during non-cancellable save; final status and user message are consistent.
- Delete/archive Post while task runs; Worker must not restore or overwrite disallowed current state.

## 6. Performance and Accessibility Gate

1. Load 100,000 owned Posts with representative body, structured fields and taxonomy links.
2. Measure combined title/body/code/tag/class/time searches; p95 first page < 2 seconds.
3. Measure article autosave and clipboard creation; p95 user-visible saved state < 2 seconds under normal local deployment.
4. Confirm timeline cursor paging is stable while new Posts are inserted.
5. At 360px width, complete clipboard capture, edit/save, AI submit and candidate field application without horizontal page scrolling.
6. Keyboard-only users can reach editor mode controls, side panel, candidate field choices and dialogs; focus returns to the invoking control.
7. Status is expressed by text/icon in addition to color; screen reader announces save, Job and conflict states without repeated noisy updates.

## 7. Final Regression Gate

```bash
cd backend
pytest
ruff check app tests
mypy app

cd ../frontend
npm run lint
npm run typecheck
npm run test
npm run test:e2e
npm run build
```

Also run the existing Posts public/publish, search, Job SSE, uploads, notifications, captures and assistant suites. The feature is not releasable if existing published Posts or RSS behavior changes unintentionally.
