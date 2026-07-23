# Quickstart Validation Checklist

Execute on a fresh Linux host with Docker Compose V2. Record evidence (command
output, screenshots) next to each item. Items requiring the production server or
real provider credentials are gated on explicit authorization.

## Prerequisites
- [ ] Docker Engine + Compose V2 present (`docker compose version`)
- [ ] 4 CPU / 8 GiB RAM, 20 GiB disk + asset/backup space

## Configure
- [ ] `cp .env.example .env`; edit non-secret values
- [ ] Create `deploy/secrets/{postgres_password,jwt_signing_key,rabbitmq_password}` (0600)
- [ ] Optional: smtp/llm/s3 secret files

## Start & migrate
- [ ] `./deploy/scripts/deploy.sh up` completes
- [ ] `docker compose ps` shows all required services healthy
- [ ] `GET /health/live` and `/health/ready` return 200
- [ ] Migration head matches `alembic heads`
- [ ] `docker compose run --rm backend python -m app.cli.main create-admin --email owner@example.com`

## Smoke tests (§6 quickstart)
- [ ] Login sets Secure HttpOnly cookies; no token in URL/localStorage
- [ ] Stop worker/AI; create text task; reload — task persists
- [ ] Drag task in week calendar; fixed-event conflict shown, never silently moved
- [ ] Daily habit generated once across two generation triggers
- [ ] Voice: record → tracked record immediately; confirm creates exactly one entity
- [ ] Photo: pending card immediately; derivative has no GPS/EXIF; original private
- [ ] SSE: disconnect, wait for job, reconnect — task center reaches final state
- [ ] Blog: draft from source; AI diff only; publish → anonymous read; unpublish → 404
- [ ] Search: keyword across types grouped + highlighted; other account isolated

## Failure injection (§7)
- [ ] Broker outage: base save works; outbox pending; recovers, executes once
- [ ] Worker crash mid-thumbnail: original readable; redelivery; no dup derivative
- [ ] Redis outage: SSE degrades to DB polling; recovers with no backfill
- [ ] Invalid LLM output: schema/business rules reject; no business mutation

## Backup / restore (§8–9)
- [ ] `docker compose --profile tools run --rm backup` writes dump+assets+manifest
- [ ] Isolated restore drill: checksums verify, pg_restore + assets + migrate
- [ ] Post-restore smoke tests pass; record measured RPO/RTO

## Deployment (only with authorization)
- [ ] Host Nginx config backed up before edit; `nginx -t` before `nginx -s reload`
- [ ] `https://llm.roguelife.de/` serves the SPA; Vue routes don't 404 on refresh
- [ ] Middleware/management ports not reachable from the public internet
