<!--
Sync Impact Report
- Version change: template -> 1.0.0
- Added principles:
  - I. Durable Capture Before Intelligence
  - II. Human Authority and Reversible Automation
  - III. Modular Monolith and Operational Simplicity
  - IV. Provider-Neutral Gateways and Validated AI
  - V. Reliable Asynchronous Work
  - VI. Private by Default and Least Privilege
  - VII. Contract-First, Test-First Delivery
  - VIII. Observable and Traceable Operations
- Added sections:
  - Architecture and Data Constraints
  - Delivery Workflow and Quality Gates
- Removed sections: none (template placeholders replaced)
- Templates:
  - updated: .specify/templates/plan-template.md
  - updated: .specify/templates/spec-template.md
  - updated: .specify/templates/tasks-template.md
- Deferred items: none
-->
# AI Assist Personal Life OS Constitution

## Core Principles

### I. Durable Capture Before Intelligence
Every user-created task, note, voice recording, image, attachment, and edit MUST be
durably stored with an owner and stable identifier before asynchronous processing begins.
AI, transcription, image processing, indexing, and notifications MUST NOT be on the
critical path for accepting user content. A failed or unavailable AI provider MUST leave
the original content accessible and retryable. Object binaries MUST live in protected
object storage, not the relational database or message broker.

Rationale: user memories and plans are the system's most valuable data; convenience
features may degrade, but accepted content may not disappear.

### II. Human Authority and Reversible Automation
AI output MUST be presented as a proposal when it changes schedules, creates
time-sensitive records, or edits authored content. Fixed events MUST never be moved by
AI. Schedule changes require a preview and a separate apply action. Voice-derived dates
and reminders require confirmation. Blog rewrites require a diff. AI-generated facts MUST
be distinguishable from user-provided facts, editable, and accompanied by confidence or
provenance where relevant. Important automation MUST support confirmation or undo.

Rationale: the product assists personal judgment; it does not silently replace it.

### III. Modular Monolith and Operational Simplicity
The MVP MUST be a modular monolith with one backend codebase, one frontend codebase,
and shared contracts. Business modules MUST expose clear internal boundaries without
premature network services. The deployment MUST remain reproducible with Docker Compose
on a personal server. New infrastructure or abstraction layers require a concrete MVP
need and a documented simpler alternative.

Rationale: a personal system must remain understandable, affordable, and maintainable by
one operator.

### IV. Provider-Neutral Gateways and Validated AI
Business modules MUST NOT call model, speech, mail, or object-storage vendors directly.
External capabilities MUST pass through typed gateways with replaceable providers,
timeouts, retry policies, usage logging, and stable domain errors. Structured AI output
MUST be validated against a versioned schema before it can enter business state. Prompts,
models, limits, and cache policies MUST be configured per scenario rather than hard-coded
inside domain services.

Rationale: provider changes and malformed output must not leak across the product.

### V. Reliable Asynchronous Work
Long-running work MUST execute asynchronously and use the database as the source of truth
for user-visible status. Business mutations and their outbox events MUST commit in one
transaction. Consumers MUST be idempotent and implement bounded retries with exponential
backoff and jitter, distributed locking where concurrency can duplicate work, and dead
letter handling for exhausted failures. Messages MUST contain identifiers and compact
parameters, never image binaries or unbounded text. Celery state is operational metadata,
not business state.

Rationale: retries, restarts, and partial outages are normal deployment conditions.

### VI. Private by Default and Least Privilege
Every user-scoped query and mutation MUST enforce ownership. Captures and posts MUST be
private by default; public blog publication is explicit. Asset access MUST be authorized
through the application or short-lived signed URLs and MUST NOT expose server paths.
Secrets MUST remain outside source control. Image derivatives intended for display MUST
remove location metadata by default, while originals follow an explicit retention policy.
Security-sensitive actions and important content changes MUST produce an audit record.

Rationale: the system stores intimate schedules, media, and personal knowledge.

### VII. Contract-First, Test-First Delivery
Database changes MUST use migrations. API, message, SSE, and structured-AI schemas MUST be
versioned contracts defined before their implementations. Each user story MUST include
tests written before implementation: unit tests for domain rules, contract tests for
external boundaries, and integration tests for persistence and asynchronous workflows.
Critical flows MUST verify data survival when AI and broker dependencies fail. A story is
not complete until its independent acceptance scenario and relevant regression suite pass.

Rationale: executable contracts make the specification trustworthy and keep asynchronous
components compatible.

### VIII. Observable and Traceable Operations
HTTP requests, outbox events, broker messages, asynchronous jobs, LLM calls, and
notifications MUST propagate a trace identifier. Structured logs MUST identify the user
and entity safely without recording secrets, tokens, raw private content, or file bytes.
Every background operation MUST expose a durable status, current step, progress, retries,
timestamps, and a user-actionable error. The UI MUST aggregate long-running work in a task
center and MUST NOT expose infrastructure vocabulary such as Celery or RabbitMQ.

Rationale: a self-hosted operator must be able to diagnose failures without inspecting
private payloads or reverse-engineering queue internals.

## Architecture and Data Constraints

- The approved MVP stack is Vue 3, TypeScript, Vite, Pinia, Vue Router, Naive UI,
  FullCalendar, and PWA support on the frontend; Python, FastAPI, SQLAlchemy 2, Alembic,
  Pydantic, and JWT authentication on the backend.
- PostgreSQL stores business data, full-text search state, outbox records, and final job
  status. Redis stores ephemeral cache, locks, and short-lived progress. RabbitMQ carries
  commands and events. MinIO or a compatible local adapter stores files.
- Initial worker topology is limited to `worker-fast` and `worker-heavy`, plus one beat
  scheduler. Queue routing MUST preserve an isolated critical notification path.
- REST is the synchronous application boundary. SSE is the one-way job-status channel.
  The MVP MUST NOT add WebSocket or GraphQL without a reviewed requirement.
- Mobile-first interaction, keyboard accessibility, clear focus states, and semantic color
  use are release requirements. Primary capture actions SHOULD complete within three user
  interactions under normal conditions.
- MVP scope is limited to the first-phase capabilities in the product specification.
  Calendar-provider sync, push notifications, vector/image semantic search, MCP, and native
  mobile clients are explicitly deferred.

## Delivery Workflow and Quality Gates

1. Each feature proceeds through specification, clarification if needed, plan, contracts
   and data model, task breakdown, implementation, and acceptance validation.
2. The plan MUST pass the Constitution Check before research and again after design.
3. Any intentional principle exception MUST be recorded in the plan's Complexity Tracking
   table with the rejected simpler option and a removal or review condition.
4. Implementation tasks MUST identify exact file paths, dependencies, tests, migrations,
   observability, and security checks. Tests precede corresponding implementation tasks.
5. Reviews MUST verify ownership filters, idempotency, schema validation, migration safety,
   fallback behavior, and protection of fixed or user-authored content.
6. Compose startup, migrations, health checks, and at least one end-to-end happy path MUST
   pass before an MVP increment is considered deployable.

## Governance

This constitution supersedes conflicting implementation convenience and generated-agent
defaults. Amendments require a written rationale, a semantic version change, an impact
report, and synchronized templates or active specifications. MAJOR versions remove or
redefine an existing guarantee, MINOR versions add a principle or materially expand a
gate, and PATCH versions clarify wording without changing obligations.

Every plan and pull request MUST state compliance or document approved exceptions.
Unexplained violations block implementation. Compliance is reviewed at specification,
design, code review, and deployment validation. Runtime development guidance lives in the
active feature plan referenced by `AGENTS.md`.

**Version**: 1.0.0 | **Ratified**: 2026-07-22 | **Last Amended**: 2026-07-22
