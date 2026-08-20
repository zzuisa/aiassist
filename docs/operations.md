# Operations Runbook

## Services

| Service | Role | Restart-safe |
|---|---|---|
| `backend` | REST + SSE + protected asset auth | yes |
| `outbox-publisher` | publishes committed outbox rows to RabbitMQ | yes (lease reclaim) |
| `worker-fast` | critical/notification/schedule/search | yes (idempotent) |
| `worker-heavy` | voice/image/llm/maintenance | yes (idempotent) |
| `celery-beat` | periodic scan commands only | single instance |
| `postgres` / `redis` / `rabbitmq` | data / cache / broker | yes |
| `nginx` | compose-internal gateway | yes |

## Provider configuration

Providers are optional; unconfigured ones degrade gracefully (base saving is
never blocked). Configure via `.env` + secret files:

- **LLM**: `LLM_PROVIDER=openai|anthropic|ollama`, `LLM_DEFAULT_MODEL`,
  key in `deploy/secrets/llm_provider_key` (Ollama needs no key).
- **Speech**: `SPEECH_PROVIDER=openai|faster_whisper|cloud`, `SPEECH_DEFAULT_MODEL`.
- **Mail**: `SMTP_HOST/PORT/USER/FROM`, `SMTP_TLS_MODE=implicit|starttls`,
  password in `deploy/secrets/smtp_password`.

Check current states (admin): `GET /api/v1/settings` → `dependencies`, or
`GET /health/dependencies`.

## Queue & job diagnostics

- Active/failed jobs: `GET /api/v1/jobs` (per user) or query `async_jobs`.
- Oldest pending outbox row (publisher lag):
  `SELECT min(created_at) FROM outbox_events WHERE status='pending';`
- Dead-letter inspection / replay (explicit, audited):
  ```bash
  docker compose run --rm backend python -m app.cli.dlq inspect voice --limit 20
  docker compose run --rm backend python -m app.cli.dlq replay voice --limit 10
  ```

## Agent batch and concurrency tuning

Agent fan-out runs inside one `worker-heavy` Celery task and shares that queue
with speech transcription and image processing. Tune these two settings
together:

| Setting | Default | Hard limit | Guidance |
|---|---:|---:|---|
| `AGENT_MAX_BATCH_OBJECTS` | 200 | 500 | Maximum objects accepted by one Agent batch; require the user to narrow larger requests. |
| `AGENT_MAX_CONCURRENCY` | 4 | 8 | Threads used inside one Agent task; start at 4 and raise only after measuring provider and database headroom. |

The bounded thread pool prevents one Agent task from creating unlimited local
work, but it does not create another Celery slot. A long Agent batch still
occupies the single `worker-heavy` slot, so queued voice and image jobs can wait
until that Celery task returns. Monitor queue wait time separately from task
runtime for all three workloads. If voice or image wait time grows, reduce the
Agent batch size or concurrency and split requests into smaller batches. Do not
configure concurrency above 8. If sustained workloads cannot meet their queue
latency target at conservative settings, move Agent work to a dedicated worker
in a separate deployment change instead of increasing the in-task thread count.

## LangGraph Agent runtime

Agent plans execute as one fixed LangGraph run on `worker-heavy`. The durable
thread key is the plan UUID, and checkpoints live in the same PostgreSQL
instance through `langgraph-checkpoint-postgres`. The `agent_execution_plans`
and step tables are public/audit projections; they are not a second scheduler.

Deployment order:

1. Build the backend image so the locked LangGraph packages are present.
2. Run the normal Alembic migration, including `0024_langgraph_runtime_refs`.
3. Start one Graph run once. Its first invocation calls the idempotent
   PostgreSQL checkpointer `setup()` before executing nodes.
4. Recreate `backend`, `worker-heavy`, `worker-fast`, `outbox-publisher`, and
   `celery-beat`, then verify both workers and the gateway.

Safe diagnostics:

```sql
SELECT id, status, runtime_state, graph_thread_id, graph_run_id, updated_at
FROM agent_execution_plans
ORDER BY updated_at DESC
LIMIT 20;
```

- `runtime_state=interrupted` means the graph is waiting for an approved or
  rejected frozen preview; the confirmation endpoint resumes the same thread.
- `runtime_state=failed` with `status=stalled|failed` is retried through the
  plan retry endpoint; do not enqueue individual step tasks.
- A cancelled plan preserves completed business effects and cancels only
  pending, queued, or confirmation-waiting work.
- Never edit LangGraph checkpoint rows manually. Recover through the plan API
  so projection events, permissions, idempotency keys, and audit records stay
  consistent.

## One-click Agent API validation

Use the dedicated Playwright flow to watch and verify the production-safe,
read-only Agent lifecycle. It checks readiness, unauthenticated rejection,
Cookie + CSRF authentication, task submission, the shared SSE stream, and the
durable terminal result.

```bash
cd frontend
npm run verify:agent:ui
```

The command securely prompts for the validation account and targets
`https://llm.roguelife.de` by default. Override the target for an isolated
stack without changing the test:

```bash
BASE_URL=http://127.0.0.1:18080 npm run verify:agent:ui
```

For a headless run and a desensitized HTML report:

```bash
npm run verify:agent
npm run verify:agent:report
```

The operator profile persists no Playwright trace, video, password, Cookie,
CSRF value, or article content. Its report contains only lifecycle status,
timing, Agent identity/version, event count, and necessary task/job IDs. CI
runs the same scenario against its isolated throwaway account and uploads the
HTML dashboard with the existing E2E diagnostics artifact.

## Storage migration (local → S3)

1. Set `STORAGE_PROVIDER=s3` + `S3_ENDPOINT_URL/S3_BUCKET/S3_REGION` and the
   `s3_access_key`/`s3_secret_key` secrets.
2. Copy existing objects from `/data/assets` into the bucket preserving keys.
3. Restart backend + worker-heavy. The storage gateway interface is unchanged;
   business modules are unaffected.

## Data retention

- `outbox_events` (published), `async_job_events`, `notification_deliveries`,
  `llm_logs`, `activity_logs` are pruned per deployment policy (maintenance job).
- Orphan assets (ref-count zero past retention) are removed by the maintenance
  worker; a failed delete becomes a maintenance job, never a data-loss rollback.

## Update procedure

1. Back up + verify a restore in staging.
2. Update image digests / lockfiles; run migrations in staging.
3. Run smoke + failure-injection tests.
4. Deploy; verify `/health/ready`, migration head, publisher + worker heartbeats.
