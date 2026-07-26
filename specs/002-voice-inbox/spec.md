# Feature Specification: Voice Inbox (accurate async voice-to-tasks)

**Feature dir**: `specs/002-voice-inbox`
**Branch**: master (operator chose to work directly on master)
**Status**: Draft → In implementation
**Created**: 2026-07-26

## Summary

The operator wants to leave a single spoken message ("一句留言") without typing,
and have the system accurately turn it into one or more todos, each placed on the
calendar at the time it mentions. Accuracy matters more than latency, so recognition
must not rely on the browser's real-time Web Speech API. Recognition runs on a cloud
provider (SiliconFlow's OpenAI-compatible `/audio/transcriptions`, model
`FunAudioLLM/SenseVoiceSmall`) — no self-hosted speech model. All processing happens
asynchronously in a background worker queue.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Record a message, get a task on the calendar (Priority: P1)

The operator taps record, speaks "明天下午三点和房东开会", stops. The audio is
uploaded and queued. Shortly after, a task "和房东开会" appears in the todo list and
on the calendar tomorrow at 15:00.

**Acceptance**:
- Recording is durably uploaded before any AI runs (Principle I).
- Transcription uses the cloud provider; a wrong provider config or outage marks the
  record `failed` and keeps the audio for retry, without losing it.
- On success a Task exists with `start_at` set from the spoken date+time in the user's
  timezone, and `due_at = start_at + duration` (default 30 min when no duration spoken).
- The task is visible on `/calendar/week` for that slot.

### User Story 2 - One message, several todos (Priority: P1)

The operator says "明天买菜、周五之前交报告、提醒我月底缴房租". The system creates
three separate tasks, each with its own date/time where stated, all linked back to the
one voice record.

**Acceptance**:
- The parse yields a list of task items; N tasks are created from one recording.
- Items without a clear time become undated todos (no `start_at`).
- All created tasks share `source_type=voice`, `source_id=<record>`.

### User Story 3 - Slow model does not block the user (Priority: P2)

The LLM/ASR call is slow (up to the provider timeout). The UI shows "处理中" and the
operator can keep using the app; the tasks appear when the worker finishes.

**Acceptance**:
- The HTTP request that accepts the recording returns immediately (record durable,
  job enqueued); transcription + parse run in the `voice` worker queue.
- The front end polls and surfaces the result (tasks appear) or a failure message.

### Edge Cases

- Empty/near-silent audio → `failed` with a friendly message; audio retained.
- Audio format not accepted by the provider → handled at the recording/encoding layer
  (record a supported format, or transcode) so transcription does not silently fail.
- Homophone/number/date recognition errors → mitigated by the LLM correction pass that
  already runs during parsing.
- Provider rate-limited/unavailable/timeout → `failed`, retryable; original audio kept.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a recorded audio message and store it durably before
  transcription or parsing begins.
- **FR-002**: System MUST transcribe audio via a provider-neutral speech gateway using a
  cloud provider; no self-hosted speech model is required.
- **FR-003**: System MUST run transcription and parsing asynchronously in the `voice`
  worker queue, not on the request path.
- **FR-004**: System MUST parse one transcript into one **or more** task candidates.
- **FR-005**: System MUST map each candidate's spoken date/time/duration to `start_at`
  and `due_at` on the created Task, using the user's timezone.
- **FR-006**: System MUST create fixed-time events with `is_fixed=true` and never let AI
  move them; flexible items are `is_ai_adjustable`.
- **FR-007**: System MUST keep every created task reversible (editable/deletable) as the
  undo path in lieu of a pre-creation confirmation step (see Deviation).
- **FR-008**: System MUST keep the original audio and transcript on any failure and allow
  retry from the last successful checkpoint.
- **FR-009**: The front end MUST default to the record-and-upload flow (not real-time Web
  Speech) and reflect processing/terminal status.

### Key Entities

- **VoiceRecord**: existing; owns the audio asset, transcript, parsed payload, status,
  and (new) links to potentially several created tasks.
- **Task**: existing; gains `start_at`/`due_at` populated from voice when applicable.

### Data Safety & AI Control *(mandatory)*

- Principle I honored: audio durable pre-AI; failures retain content.
- Principle IV honored: transcription and LLM both behind typed gateways with strict,
  versioned schema validation.
- **Deviation from Principle II** (Human Authority): voice-derived dated tasks are
  normally required to be *confirmed* before creation. The operator has explicitly chosen
  auto-creation for speed. Mitigation satisfying "confirmation OR undo": created tasks are
  fully editable and deletable, are provenance-tagged `source_type=voice`, and fixed
  events remain non-AI-movable. This deviation is intentional and recorded here.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A spoken dated message results in a task on the calendar at the correct slot
  in the operator's timezone.
- **SC-002**: A multi-item message produces the correct number of separate tasks.
- **SC-003**: The accept-recording request returns without waiting for AI.
- **SC-004**: Chinese recognition accuracy is materially better than the browser Web
  Speech baseline (validated by spot-checking real recordings).

## Assumptions

- SiliconFlow `/audio/transcriptions` (SenseVoiceSmall) is reachable with the existing
  LLM key/base URL; limits ≤1h / ≤50MB per file.
- Habits/collections routing is out of scope; voice creates tasks only (operator choice).
- Real-time Web Speech path is deprecated (kept only as a no-op fallback / removed from
  the primary UI).
