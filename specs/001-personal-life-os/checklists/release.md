# Release Checklist

## Automated gates (local run, real PostgreSQL 18.4)

| Gate | Command | Result |
|---|---|---|
| Backend lint | `ruff check app tests` | ✅ pass |
| Backend format | `ruff format --check app tests` | ✅ pass |
| Backend types | `mypy` | ✅ pass (115 files) |
| Backend tests | `pytest` (unit/contract/integration/security/reliability/performance) | ✅ 166 passed, 1 skipped |
| Frontend types | `vue-tsc --noEmit` | ✅ pass |
| Frontend lint | `eslint . --max-warnings 0` | ✅ pass |
| Frontend tests | `vitest run` | ✅ 55 passed |
| Frontend build | `vite build` | ✅ succeeds |
| Compose config | `docker compose --profile s3 --profile tools config` | ✅ valid |
| Migrations | `alembic upgrade head` / `downgrade` / `check` | ✅ no drift, reversible |

Skipped: `broker` marker (real RabbitMQ) — runs in CI's `rabbitmq` service; the
sandbox cannot boot RabbitMQ (erlang cookie `eacces`). Outbox/publisher logic is
covered against real PostgreSQL with an injected publisher.

## Coverage of Constitution gates

- ✅ Durable acceptance before AI: task/capture/voice save-first + pending outbox.
- ✅ AI preview/confirm/apply, fixed events never AI-moved (schedule + assistant).
- ✅ Modular monolith + Compose; no business microservices.
- ✅ All AI/speech/mail/storage via gateways; strict schema validation.
- ✅ Outbox, idempotency keys, retries, DLQ, locks, trace IDs.
- ✅ Ownership isolation, private-by-default, authorized asset access (X-Accel).
- ✅ Versioned REST/SSE/message/AI contracts under `contracts/`.
- ✅ Tests precede implementation per phase; failure paths covered.
- ✅ User-visible task center; `async_jobs` is the durable business truth.

## Measurable success criteria

- ✅ SC-001 text save p95 < 2s (perf test).
- ✅ SC-005 zero AI moves of fixed events (schedule + assistant tests).
- ✅ SC-006 voice date/time candidates require confirmation.
- ✅ SC-008 search p95 within budget (bounded-seed perf test).
- ✅ SC-010 duplicate delivery x10 → 1 effect (reliability test).

## Known limitations

- Docker image build and the `broker` test suite require network / a bootable
  RabbitMQ, both unavailable in the authoring sandbox; both run in CI.
- Production deploy + host Nginx changes are gated on explicit authorization and
  were intentionally NOT executed (deployment files created and validated only).
- E2E Playwright journeys are written but skip without `E2E_EMAIL/E2E_PASSWORD`
  against a running stack.
