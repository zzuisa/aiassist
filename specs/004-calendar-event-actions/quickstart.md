# Quickstart: 日历事件快捷操作与视觉优化

## Prerequisites

- Docker Compose stack is healthy and migrations have completed.
- A test user exists with a configured timezone.
- For email timing checks, SMTP is configured to a test mailbox; unconfigured-mail behavior is tested separately.
- Use JPEG/PNG/WebP fixtures, including one invalid image and one image containing GPS EXIF metadata.

## 1. Apply migration and run focused backend tests

```bash
docker compose run --rm api alembic upgrade head
docker compose run --rm api pytest \
  tests/contract/test_calendar_event_actions_api.py \
  tests/unit/test_important_reminder_rules.py \
  tests/integration/test_calendar_event_actions.py \
  tests/integration/test_task_note_assets.py \
  tests/integration/test_important_reminders.py \
  tests/reliability/test_calendar_event_action_failures.py \
  tests/security/test_task_note_asset_security.py
```

Expected: migration succeeds from the previous head; contract schemas match; ownership, idempotency, partial failures and data survival pass.

## 2. Run focused frontend tests

```bash
docker compose run --rm frontend npm test -- \
  tests/component/calendar-event-actions.spec.ts \
  tests/component/calendar-event-note.spec.ts
docker compose run --rm frontend npm run typecheck
```

Expected: event content order, popover interactions, status combinations, past-slot classes and multi-batch upload behavior pass.

## 3. Desktop and mobile event actions

1. Create a scheduled event at least five hours in the future.
2. In a desktop browser, left-click the event; in mobile emulation, lightly tap it.
3. Verify the popover stays in the visible viewport and offers completion, importance and note actions.
4. Mark the event completed and important.
5. Verify the completion emoji and soft red background coexist and the title remains above the time.
6. Reload, reopen the popover and verify both states remain.
7. Cancel completion and importance; verify the emoji/background disappear and the unsent reminder is cancelled.

## 4. Important reminder lifecycle

1. Mark a future event important and inspect the returned reminder summary.
2. Verify `trigger_at` equals `start_at - 4 hours`.
3. Move the event before the reminder fires; verify the same reminder record is rescheduled.
4. Repeat the state update and simulate worker redelivery; verify no duplicate email delivery.
5. Mark an event less than four hours away important; verify the reminder is scheduled immediately.
6. Test an already-started event, an event without `start_at`, and an unconfigured SMTP environment; verify the user-facing states are respectively `not_applicable`, `missing_start`, and `unconfigured` without rolling back importance.

## 5. Multi-batch event note images

1. Open the event note editor and enter text.
2. Select five valid images as batch one, save, and wait for preview processing.
3. Reopen and append two more batches, for at least twelve total images.
4. Verify every ready preview is sanitized and associated with the correct user, task and note.
5. Include one corrupt or unsupported file in a batch; verify valid files remain and only the failed item offers retry.
6. Reload the page and verify note text and every successful attachment remain in stable order.

## 6. Ownership and private access

1. Create a second user and attempt note read/update, attachment association and asset access using the first user's identifiers.
2. Verify every attempt returns a non-disclosing not-found response.
3. Verify API responses never expose object keys or server paths.
4. Verify default image rendering requests sanitized previews; original access occurs only after an explicit download request.

## 7. Past-time visual regression

1. Freeze the browser time within a displayed week containing past, current and future slots.
2. Verify only elapsed grid slots use the muted background.
3. Place normal, completed, important and completed+important events in elapsed slots.
4. Verify names, time ranges, emoji and important background remain readable in light and dark themes.
5. Advance the clock across a slot boundary and verify the past-time class updates within one minute.

## 8. Full regression

```bash
docker compose run --rm api pytest
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run build
docker compose run --rm frontend npm run test:e2e -- tests/e2e/calendar-event-actions.spec.ts
```

Expected: existing drag/resize, fixed-event protection, Today/calendar synchronization, captures, notifications and task flows continue to pass.
