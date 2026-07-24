# Quickstart Validation Checklist

Execute on a fresh Linux host with Docker Compose V2. Record evidence (command
output, screenshots) next to each item. Items requiring the production server or
real provider credentials are gated on explicit authorization.

## Prerequisites
- [x] Docker Engine + Compose V2 present (`docker compose version`) — 2026-07-23
- [x] 4 CPU / 8 GiB RAM, 20 GiB disk + asset/backup space — 4 CPU, 15 GiB RAM, 34 GiB free

## Configure
- [x] `cp .env.example .env`; edit non-secret values — production origin configured
- [x] Create `deploy/secrets/{postgres_password,jwt_signing_key,rabbitmq_password}` (0600)
- [ ] Optional: smtp/llm/s3 secret files

## Start & migrate
- [x] `./deploy/scripts/deploy.sh up` completes — 2026-07-23
- [x] `docker compose ps` shows all required services healthy
- [x] `GET /health/live` and `/health/ready` return 200
- [x] Migration head matches `alembic heads` — `0008_posts`
- [ ] `./deploy/scripts/deploy.sh create-admin owner@example.com`

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
- [x] `docker compose --profile tools run --rm backup` writes dump+assets+manifest — checksums verified
- [ ] Isolated restore drill: checksums verify, pg_restore + assets + migrate
- [ ] Post-restore smoke tests pass; record measured RPO/RTO

## Deployment (only with authorization)
- [x] Host Nginx config backed up before edit; BaoTa `nginx -t` passed before reload
- [x] `https://llm.roguelife.de/` serves the SPA; `/settings` refresh returns 200
- [x] Middleware/management ports are not published by the AI Assist Compose project
