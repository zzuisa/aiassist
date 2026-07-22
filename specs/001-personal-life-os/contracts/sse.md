# SSE Contract: Background Job and Notification Events

## Endpoint

`GET /api/v1/events/jobs`

- Content type: `text/event-stream; charset=utf-8`
- Authentication: same-origin `__Host-aiassist_access` HttpOnly Cookie
- Cache: `Cache-Control: no-cache`
- Proxy: `X-Accel-Buffering: no`; Nginx route also sets `proxy_buffering off`
- Reconnect: server suggests `retry: 3000`; browser supplies `Last-Event-ID`
- One connection per browser tab. The global jobs store distributes events to pages.

The endpoint validates the access session before opening and periodically during the stream. If the session can no
longer be renewed, it closes with HTTP 204 on the next connection so the browser stops automatic reconnect; the client
then resolves auth state through `/auth/me` or `/auth/refresh`.

## Durable source and delivery

1. Every meaningful job transition updates `async_jobs` and appends `async_job_events` in the same PostgreSQL transaction.
2. After commit, the process publishes a small Redis wakeup containing user ID and latest event ID.
3. SSE treats Redis only as a wakeup and queries PostgreSQL for rows after its current cursor.
4. If Redis is unavailable, SSE polls PostgreSQL at a bounded interval; correctness is unchanged.
5. With a valid `Last-Event-ID`, the server replays later retained events in order.
6. With no cursor or an expired cursor, the server sends a `jobs.snapshot` followed by new events.
7. Delivery is at least once. Clients deduplicate by event ID and apply a job only if `job_version` is newer.

## Wire examples

### Snapshot

```text
id: 21492
event: jobs.snapshot
retry: 3000
data: {"snapshot_at":"2026-07-22T10:30:00Z","jobs":[{"job_id":"b4a6...","job_version":3,"job_type":"capture.analyze","status":"processing","progress":35,"current_step":"正在生成预览图","retry_count":0,"updated_at":"2026-07-22T10:29:58Z"}],"notifications":[]}

```

### Progress update

```text
id: 21493
event: job.updated
data: {"job_id":"b4a6...","job_version":4,"status":"processing","progress":65,"current_step":"正在分析内容","updated_at":"2026-07-22T10:30:04Z","trace_id":"0af7651916cd43dd8448eb211c80319c"}

```

### Waiting for confirmation

```text
id: 21494
event: job.waiting_user
data: {"job_id":"d8c1...","job_version":5,"status":"waiting_user","progress":100,"current_step":"请确认语音识别结果","entity":{"type":"voice_record","id":"cc1d..."},"action":{"kind":"open_voice_confirmation","label":"查看并确认"},"updated_at":"2026-07-22T10:30:11Z"}

```

### Failure

```text
id: 21495
event: job.failed
data: {"job_id":"b4a6...","job_version":6,"status":"failed","progress":65,"current_step":"图片分析未完成","error":{"code":"VISION_PROVIDER_TIMEOUT","message":"内容已保存，可稍后重新分析","retryable":true},"updated_at":"2026-07-22T10:30:40Z","trace_id":"0af7651916cd43dd8448eb211c80319c"}

```

### Notification

```text
id: 21496
event: notification.created
data: {"notification_id":"ade4...","type":"task_due","title":"联系房东","body":"将在 30 分钟后到期","entity":{"type":"task","id":"923a..."},"created_at":"2026-07-22T10:31:00Z"}

```

### Heartbeat

Every 15–30 seconds, when there is no event:

```text
: heartbeat 2026-07-22T10:31:15Z

```

Heartbeat comments do not advance the durable event cursor.

## Event catalog

| Event name | When emitted | Required data |
|---|---|---|
| `jobs.snapshot` | Initial connect, invalid/expired cursor | `snapshot_at`, jobs, notifications |
| `job.updated` | Queued, processing, progress or retry transition | job ID/version/status/progress/step |
| `job.waiting_user` | Voice, schedule or blog output requires review | entity/action plus job fields |
| `job.completed` | Durable result committed | result summary/reference plus job fields |
| `job.failed` | Terminal attempt committed | stable error code, safe message, retryable |
| `job.cancelled` | Cancellation is durable | job ID/version and preserved entity reference |
| `notification.created` | In-app notification committed | notification fields and optional entity |

## JSON payload rules

- Maximum individual data payload: 32 KiB. Larger results are fetched from the referenced REST endpoint.
- `current_step`, action labels and error messages are user-facing Chinese text, not task/queue/provider names.
- Never include Celery IDs, RabbitMQ routes, stack traces, access tokens, signed URLs, prompts, raw transcripts,
  private article bodies or image metadata.
- `trace_id` may be shown in a copyable diagnostic detail but is not the primary error message.
- Event payload schemas are strict and versioned in implementation. Additive optional fields are permitted within v1;
  removing/renaming fields or changing meaning requires a new event version/name.

## Client algorithm

1. On login, fetch `GET /jobs` and create EventSource.
2. For `jobs.snapshot`, replace only task-center entities with equal/older versions; do not discard unsaved UI state.
3. For job events, ignore duplicate ID or `job_version <= current.job_version`.
4. Invalidate the affected module entity query after completed/waiting_user, then open UI only on explicit user action.
5. On network error, show a small “正在重新连接” state; do not emit repeated Toasts.
6. After reconnection, rely on replay/snapshot. If repeated failure persists, poll `GET /jobs` with backoff.
7. On logout, call `EventSource.close()` and clear private stores.

## Acceptance tests

- Disconnect before three transitions, reconnect with last ID, and observe all retained events in order.
- Reconnect with an expired ID and reconcile through one snapshot.
- Deliver the same event twice and verify a single UI state change.
- Disable Redis and verify events arrive by database polling.
- Attempt cross-user cursor/job IDs and verify no information is exposed.
- Expire auth during a stream and verify clean stop/refresh behavior without token in URL.
