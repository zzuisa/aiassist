# Backup & Restore

AI Assist's authoritative state is **PostgreSQL** (business data, outbox, jobs,
search) and the **private asset volume** (`/data/assets`). Redis, RabbitMQ and
Celery hold only transient state and are **not** part of a backup.

Default targets: **RPO 24h**, **RTO 2h**. Adjust to your risk tolerance.

## Backup

```bash
docker compose --profile tools run --rm backup
```

Each run writes `data/backups/<timestamp>/`:

| File | Contents |
|---|---|
| `database.dump` | `pg_dump -Fc` custom-format dump (selective/parallel restore) |
| `assets.tar.gz` | private asset volume snapshot |
| `manifest.json` | timestamp, checksums, asset count, migration head |

**You must copy each backup off-host and encrypt it.** Secrets are backed up
separately (see `deploy/secrets/README.md`) and never committed.

## Restore (isolated drill — do quarterly)

On a clean host/volume:

```bash
# 1. Bring up only the database.
docker compose up -d postgres
# 2. Restore (verifies checksums, pg_restore, assets, migrations).
docker compose --profile tools run --rm \
  -v "$PWD/data/backups/<timestamp>:/restore:ro" \
  backup /app/deploy/scripts/restore.sh /restore
```

After restore:

1. Inject secrets and start the app processes.
2. Set any interrupted `processing` jobs to a retryable state (they re-run
   idempotently; the outbox publisher replays pending events).
3. Run smoke tests: login, text save, asset read, SSE, email (if configured).
4. Record measured RPO/RTO.

## What is intentionally NOT restored

- Redis cache/locks — rebuilt on demand.
- RabbitMQ queues — the outbox re-publishes pending events after restore.
- Celery result state — business truth is in `async_jobs`.
