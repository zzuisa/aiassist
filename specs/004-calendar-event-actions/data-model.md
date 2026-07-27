# Data Model: 日历事件快捷操作与视觉优化

## Existing entities reused

### Task

Existing fields used by this feature:

| Field | Type | Rule |
|---|---|---|
| `id` | UUID | Stable event identifier |
| `user_id` | UUID FK | Every lookup/mutation filters by owner |
| `title` | string | Primary calendar event content |
| `status` | enum-like string | `completed` shows emoji; reopening writes `todo` |
| `importance` | small integer 0–4 | Values `> 0` render as important; popover toggle writes 4 or 0 |
| `start_at` | zoned datetime, nullable | Anchor for the dedicated four-hour reminder |
| `due_at` | zoned datetime, nullable | Calendar end time; not the important reminder anchor |
| `completed_at` | zoned datetime, nullable | Set on completion, cleared when completion is cancelled |
| `version` | integer | Required optimistic concurrency token for state changes |

State transitions:

```text
todo/in_progress ──complete──> completed
completed ──undo complete──> todo

importance 0 ──mark important──> importance 4
importance 1..4 ──remove important──> importance 0
```

The calendar events query includes scheduled `todo`, `in_progress`, and `completed` tasks. The
unscheduled list includes only `todo` and `in_progress` tasks.

## Modified entity

### Reminder

Existing reminder rows are extended to make relative-time behavior explicit.

| Field | Type | Rule |
|---|---|---|
| `purpose` | string | `custom` (default) or `important_start_4h` |
| `anchor` | string | `absolute`, `due_at`, or `start_at` |
| `task_id` | UUID FK | Required owner task |
| `channel` | string | Dedicated important reminder is `email` |
| `trigger_at` | zoned datetime | Stored scan time; recomputed from the anchor |
| `offset_minutes` | integer, nullable | 240 for `important_start_4h` |
| `is_critical` | boolean | True for important reminder routing |
| `status` | string | scheduled, claimed, sent, failed, cancelled |
| `idempotency_key` | string | Stable per user/task/purpose, not based on movable trigger time |
| `last_error` | text, nullable | User-safe status derives from this and delivery state |

Validation and indexes:

- `purpose` and `anchor` use check constraints.
- A partial unique index on `(user_id, task_id, channel, purpose)` where
  `purpose='important_start_4h'` guarantees one dedicated reminder per task.
- Existing due-scan index on `(status, trigger_at)` remains.
- Existing custom reminders retain their current idempotency behavior.

Important reminder transitions:

```text
not present/cancelled ──importance > 0 + future start──> scheduled
scheduled/claimed ──start changes──> scheduled at recomputed trigger
scheduled/claimed ──importance = 0──> cancelled
scheduled/claimed ──due scan──> sent (delivery tracks actual email result)
sent ──toggle/reschedule──> sent (no duplicate email)
```

Derived API states are `scheduled`, `sending`, `sent`, `failed`, `unconfigured`,
`missing_start`, and `not_applicable`.

## New entities

### TaskNote

One mutable user note per task.

| Field | Type | Null | Rule |
|---|---|---:|---|
| `id` | UUID PK | no | Stable note identifier |
| `user_id` | UUID FK users | no | Must equal owning task user |
| `task_id` | UUID FK tasks | no | Unique; cascade on physical task removal |
| `content` | text | no | Maximum 20,000 characters; empty only if at least one active asset exists |
| `version` | integer | no | Starts at 1 and increments on text updates |
| `created_at` | zoned datetime | no | Server timestamp |
| `updated_at` | zoned datetime | no | Server timestamp |
| `deleted_at` | zoned datetime | yes | Reserved for recoverable removal |

Constraints and indexes:

- Unique `(user_id, task_id)`.
- Index `(user_id, task_id, deleted_at)` for owned lookup.
- Service validates task ownership before create/read/update.

### TaskNoteAsset

One logical image attached to a TaskNote.

| Field | Type | Null | Rule |
|---|---|---:|---|
| `id` | UUID PK | no | Stable attachment identifier exposed to clients |
| `user_id` | UUID FK users | no | Same owner as note, task, and upload session |
| `note_id` | UUID FK task_notes | no | Cascade on physical note removal |
| `upload_id` | UUID FK upload_sessions | no | Unique completed `task_note_image` upload |
| `storage_key` | string | no | Private original object key; never returned directly |
| `preview_storage_key` | string | yes | Sanitized preview object key |
| `filename` | string | no | Original display filename |
| `media_type` | string | no | JPEG, PNG, or WebP after validation |
| `byte_size` | bigint | no | Stored original size |
| `sha256` | string | yes | Integrity/deduplication hint, not identity |
| `width` / `height` | integer | yes | Filled after image validation |
| `position` | integer | no | Stable display order; append uses next value |
| `processing_status` | string | no | pending, processing, ready, failed, deleted |
| `processing_version` | string | yes | Makes derivative processing idempotent |
| `last_error` | string | yes | Stable user-actionable failure category |
| `async_job_id` | UUID | yes | Durable job shown through existing task center |
| `created_at` | zoned datetime | no | Server timestamp |
| `deleted_at` | zoned datetime | yes | Excluded from normal reads |

Constraints and indexes:

- Unique `upload_id` prevents one uploaded object from being attached twice.
- Unique `(note_id, position)` preserves deterministic ordering.
- Check constraints protect processing status and allowed image types.
- Index `(user_id, note_id, deleted_at)` supports owned list/access checks.

### UploadSession modification

Add `task_note_image` to the allowed `purpose` values. It uses the existing image byte-size limit,
declared MIME validation and completed-object lifecycle. A completed upload that never becomes an
attachment is reclaimed by the maintenance worker only after it expires and an ownership-safe lookup
confirms that no TaskNoteAsset references it.

## Relationships

```text
User 1 ── * Task
Task 1 ── 0..1 TaskNote
TaskNote 1 ── * TaskNoteAsset
UploadSession 1 ── 0..1 TaskNoteAsset
Task 1 ── * Reminder
Task 1 ── 0..1 Reminder[purpose=important_start_4h, channel=email]
```

## Transaction boundaries

1. Task status/importance update, completed timestamp, reminder lifecycle change, activity log, and
   Outbox event commit in one database transaction.
2. Binary upload completes in private object storage before a TaskNoteAsset is accepted.
3. TaskNote/TaskNoteAsset, activity log, durable async job, and image-processing Outbox event commit
   together. If this transaction fails, the completed upload remains unattached and cleanup-eligible.
4. Preview generation updates the asset/job state in a worker transaction; retries use asset ID and
   processing version so redelivery does not create duplicate objects.

## Ownership invariants

- `task.user_id == note.user_id == asset.user_id == upload.user_id` is validated before every write.
- Asset access first resolves the owned task and note, then the owned asset; foreign identifiers return
  the same not-found response as missing identifiers.
- Storage keys, internal paths, raw errors and EXIF metadata are never returned in API responses.
