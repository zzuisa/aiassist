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
