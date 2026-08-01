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

AI Assist 完整优化还会先执行 Blog Enhancement Orchestrator 的共享诊断。能力注册通过后端环境变量 `BLOG_CAPABILITIES_JSON` 注入，例如只启用本地流程图能力时可传入不含 endpoint/secret 的清单；未启用的视觉能力应在结果中标记 `skipped` 或 `unavailable`，而不是生成装饰性内容。

### 可视化能力

- `visualize`：默认启用。面向普通读者时模型优先输出受限的 `visual-plan` 节点/关系 JSON，后端做结构校验，Worker 使用 CJK 字体直接生成紧凑 PNG 资产，存入私有对象存储并把 Markdown 图片插入正文导语后；技术图继续兼容 Mermaid。
- `answers-charts`：默认启用。模型只能使用正文中已有的统一口径数据，输出 ECharts 结构；后端校验后在候选正文和阅读预览中渲染图表。
- `answers-images` / `imagegen`：默认关闭。需要注册 `type=http-api`、`enabled=true` 和 HTTPS `endpoint`，密钥仅通过 `token_file` 注入，不能写入环境变量或 Prompt。图片服务需要返回 `url`、`data[].url`、`images[].url` 或 `results[].url` 之一。

要允许图片能力参与自动优化，还需显式设置 `BLOG_ALLOW_RETRIEVED_IMAGES=true` 或 `BLOG_ALLOW_GENERATED_IMAGES=true`。例如 SiliconFlow 兼容接口可以使用 `https://api.siliconflow.cn/v1/images/generations`，并在能力项中配置 `model` 和现有 LLM provider 的 `token_file`；不开启开关时不会产生图片调用。

流程图和图表不需要额外的模型或 API Key；它们由当前 Blog Enhancement LLM 生成结构化内容，再由本地渲染器执行。图片能力只有在明确注册服务后才会产生外部调用。

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

Validated locally for US8 on 2026-08-01:

- PostgreSQL 18 migration from an empty database reached `0017_taxonomy_alias_governance`.
- US8 contract, integration and reliability selection: 7 passed, including hierarchy/ownership, aliases, stop words, atomic/audited merge, durable deduplication and keyword recomputation redelivery.
- Backend Ruff, format and mypy: passed (145 typed source files).
- Frontend ESLint/typecheck, all 147 unit/component tests and production build: passed under Node 22.
- Article property controls retain attached disabled values while excluding other disabled choices and expose governed aliases/synonyms.

### US9 — Word-cloud exploration

1. Prepare posts across two years with tags/keywords and configured stop words.
2. Request a keyword snapshot for one year and wait for the durable Job.
3. Verify min frequency, max terms and stop-word exclusion.
4. Click a term and confirm the Post list receives the canonical keyword filter.
5. Force rebuild failure and verify the last successful snapshot still renders with stale/error indication.

**Pass**: word cloud is an optional derived view and never affects search or article access.

### Priority increment — Deployment update transparency

1. Write a new release entry and open the authenticated application in a browser with no matching `aiassist:last-seen-release` value.
2. Confirm the “本次更新内容” dialog shows the version, change summary and deployment time, then follow “查看更新历史”.
3. Confirm the history panel marks the newest entry as “当前运行” and shows commit, Git push, deployment status and changed files.
4. Close the dialog, refresh and confirm the same version does not show again; create a new release entry and confirm it does.
5. Run `deploy.sh up` with a dirty worktree and verify commit/push happens before image build; simulate push failure and verify the script exits non-zero without building.

**Pass**: every successful deployment is traceable to a pushed commit and users can understand the current and historical versions without exposing secrets.

### Priority increment — 移动端博客与结构化主分类

1. At a 360px viewport, open the blog list and confirm the category filter, article rows and more-actions fallback fit without horizontal page scrolling.
2. Swipe an article right to expose “归类” and left to expose “归档/丢弃”; a short or vertical gesture must return the row to its original position.
3. Use the more-actions fallback to reach the same actions without a gesture, then open the “分类” page and confirm the bounded category tree is available.

**Pass**: category is the first structured organizing action, mobile gestures are reversible/cancelable at the row level, and every gesture has an accessible button path.

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
| 18 | Mobile category-first list | component + 360px E2E | Category filter, row actions and accessible fallback fit at 360px |
| 19 | Primary category projection | contract + component | List rows expose category_id and category filter scopes results |
| 20 | Mobile bottom navigation | component + production build | Fixed navigation remains visible above content with safe-area clearance |
| 21 | Mobile bottom navigation width matrix | 360/375/390px E2E | All primary entries remain clickable without horizontal overflow |
| 22 | Blog deep search | contract + integration | Committed title/body/source/taxonomy/structured fields are searchable immediately |
| 23 | Blog timeline fallback | contract + component | Occurrence time is preferred and creation time is explicitly labeled as fallback |
| 24 | Deployment update popup | component + E2E | Unseen release shows version, changes, time and history navigation |
| 25 | Release history status | component + production build | Current/history entries show deployment, commit and push status with expandable files |
| 26 | Git deployment gate | shell integration + deployment | Commit and push complete before build; push failure stops deployment with non-zero status |

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
6. At 360px width, complete category filtering, row action fallback and category navigation without horizontal page scrolling.
7. At 360px, 375px and 390px widths, the fixed bottom navigation stays above page content and the final content remains reachable.
8. Keyboard-only users can reach editor mode controls, side panel, candidate field choices, dialogs and primary navigation; focus returns to the invoking control.
9. Status is expressed by text/icon in addition to color; screen reader announces save, Job and conflict states without repeated noisy updates.

## 7. Mobile and category validation evidence

Validated for this priority increment on 2026-07-31:

- `npm run typecheck`: passed.
- Targeted ESLint and `git diff --check`: passed.
- Node 24 container: `app-shell.spec.ts`, `blog-mobile.spec.ts` and `blog-taxonomy.spec.ts`, 6 tests passed.
- Node 24 container: `blog-discovery.spec.ts`, 5 search/timeline tests passed; the full focused set is 11 tests passed.
- Production deployment: frontend `vue-tsc` + Vite build passed, migrations applied to head, and backend/frontend/workers/Beat/Outbox/Nginx health checks passed; gateway verification completed at `http://127.0.0.1:18080`.
- 360px Playwright coverage in `frontend/tests/e2e/blog-content-management.spec.ts` was executed with the isolated CI account on 2026-08-01 and passed together with the authenticated desktop and accessibility paths.
- Bottom-navigation production coverage is present in `frontend/src/app/AppShell.vue`; the deployed build includes fixed positioning, `z-index`, opaque background, safe-area padding and content clearance.
- Backend category/list contract coverage is present in `backend/tests/contract/test_blog_content_api.py`; the runtime image intentionally excludes pytest, so that suite was not executed inside the deployed container.
- Release popup/history component coverage is present in `frontend/tests/component/app-shell.spec.ts` and `frontend/tests/component/release-history.spec.ts`; release metadata is served without service-worker precache so every deployment is fetched fresh.
- `deploy/scripts/deploy.sh` commits and pushes the worktree before building images, then commits and pushes the release history metadata; release metadata contains no secrets or article content.
- Release verification on 2026-07-31: source commits `e7e508d`, `07ed9d0` and release metadata commits `1b70e24`, `2361f08` are pushed to `origin/005-blog-content-management`; `/release-history.json` returned HTTP 200 with mode 644, and all Compose healthchecks plus both Worker pongs passed.

## 8. Final Regression Gate

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

## 9. Continuous Integration Gate

`.github/workflows/ci.yml` runs for every branch push and pull request. The required
continuous checks are:

1. Backend Ruff formatting/lint and mypy.
2. Backend unit, contract, integration, security and reliability tests with at least 70%
   application coverage, followed by the real-broker round trip.
3. Frontend lint, typecheck, unit/component tests and production build.
4. Compose configuration validation with every required secret-file placeholder.
5. An isolated Compose startup, migration and health check followed by authenticated blog
   and 360px Playwright smoke tests. Test credentials are CI-only constants and are never
   production credentials.
6. A scheduled or manually dispatched 100,000-row performance run with its JUnit report

US7 deep-search acceptance was executed on 2026-08-01:

- Push CI run `30708903463` passed backend quality, PostgreSQL integration/security/broker
  suites, frontend lint/type/tests/build, Compose configuration and isolated E2E.
- Manual CI run `30709016223` passed the 100,000-Post performance job in 1m21s and
  uploaded `performance-100k-results`; the same run also passed every regular gate.
- Search coverage includes committed data before index refresh, idempotent Post index
  refresh, CJK/code/source/taxonomy/structured fields, ownership isolation, safe
  highlights, occurrence-time fallback and deterministic timeline pages.
   retained as a workflow artifact.

`deploy/scripts/deploy.sh up` pushes the source and release-history commits, discovers the
GitHub Actions run for that exact release commit, and waits for a successful result before
pulling middleware or building application images. A missing, timed-out or failed workflow
stops deployment with a non-zero status. `DEPLOY_SKIP_CI_GATE=1` is reserved for an explicit
operator emergency and must not be used for routine deployments.

### 2026-08-01 execution evidence

- Release commit `8212e49` passed [GitHub Actions CI run 30703186458](https://github.com/zzuisa/aiassist/actions/runs/30703186458) before deployment started.
- Backend Ruff, format, mypy, unit/contract/integration/reliability/security tests and the real RabbitMQ round trip passed; aggregate line coverage was 76.17%, above the 70% gate.
- Frontend lint, typecheck, all unit/component tests and production build passed. The isolated Compose E2E job applied migrations, verified gateway and Worker routing, then passed 11 authenticated blog/accessibility tests including the 360px mobile path; one external-AI test was intentionally skipped because CI does not inject a production model credential.
- The same release commit was deployed through `deploy/scripts/deploy.sh up`. Migration exited successfully; gateway, backend, frontend, PostgreSQL, Redis, RabbitMQ, fast/heavy Workers, Beat and Outbox publisher all passed health checks, and both Worker ping checks returned `OK`.
- Failed predecessor runs stopped before image build, confirming that an unsuccessful exact-commit CI result cannot be reported as a successful deployment.
