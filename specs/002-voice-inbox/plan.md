# Implementation Plan: Voice Inbox

**Spec**: [spec.md](./spec.md) · **Branch**: master · **Date**: 2026-07-26

## Constitution Check

| Principle | Status |
|---|---|
| I. Durable Capture Before Intelligence | PASS — audio uploaded/stored before job runs |
| II. Human Authority / Reversible Automation | DEVIATION (recorded in spec) — auto-create with edit/delete as undo; fixed events not AI-moved |
| III. Modular Monolith / Simplicity | PASS — no new services; reuse existing queues/gateways |
| IV. Provider-Neutral Gateways / Validated AI | PASS — speech + LLM behind typed gateways, strict schema |
| V. Reliable Async Work | PASS — `voice` queue, checkpointed retries |
| VI. Private by Default | PASS — same-owner scoping, no new exposure |
| VII. Contract-First, Test-First | PASS — add `voice-task.v2` contract + drift test; pipeline tests |
| VIII. Observable/Traceable | PASS — job transitions + logs retained |

## Technical Approach

Reuse the existing audio path end-to-end; the only new behavior is (a) enabling the
cloud ASR provider, (b) parsing to a **list**, (c) writing calendar fields, and (d)
making the front end default to recording.

### Backend

- **Config**: `SPEECH_PROVIDER=openai`, `SPEECH_DEFAULT_MODEL=FunAudioLLM/SenseVoiceSmall`
  (reuses `llm_base_url` + `resolved_llm_provider_key`). `OpenAIWhisperProvider` already
  posts to `{base}/audio/transcriptions`.
- **Schema v2**: add `VoiceTasksV1 { tasks: list[VoiceTaskV1] }` (strict) →
  `contracts/schemas/voice-tasks.v1.json`; keep `VoiceTaskV1` as the item. Update the
  schema-drift test + checked-in contract.
- **Parse**: `run_pipeline` requests the list schema; system prompt instructs "split the
  message into independent actionable tasks" plus the existing zh ASR-correction rules.
- **Task creation**: for each item, create a Task and set:
  - `start_at` = combine(`local_date`,`local_time`) in user's `timezone` → aware UTC.
  - `due_at` = `start_at + duration_minutes` (default 30 when timed but no duration).
  - undated items: leave `start_at`/`due_at` null (plain todo).
  - `is_fixed` for `fixed_event`; else `is_ai_adjustable`.
  - one `EntityRelation(converted_to)` per task; record → `confirmed`.
- **Audio format**: verify SenseVoice accepts `webm/opus`; if not, either record `wav`
  client-side or add a lightweight ffmpeg transcode in the transcribe checkpoint.

### Frontend

- `TodayPage` primary voice entry becomes `VoiceRecorder` (record→upload→queue). Existing
  `onVoiceCreated` polling already handles `uploaded/parsing → confirmed/failed`.
- Keep `LiveVoiceInput` out of the primary flow (deprecated).

## Risks

- **Audio format** (primary): mitigations above; verified before shipping increment 1.
- **Provider limits/latency**: async worker absorbs latency; failures are retryable.
- **Contract drift test**: must regenerate `voice-tasks.v1.json` to match the Pydantic model.
