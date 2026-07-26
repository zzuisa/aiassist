# Tasks: Voice Inbox

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Branch**: master

Increment 1 = core async cloud-ASR path onto the calendar (single task first).
Increment 2 = decompose one message into multiple tasks.

## Increment 1 — cloud ASR + async + calendar

- [x] T001 Enable cloud ASR in `.env`: `SPEECH_PROVIDER=openai`,
      `SPEECH_DEFAULT_MODEL=FunAudioLLM/SenseVoiceSmall`.
- [x] T002 Backend: write calendar fields on voice-created Task — add a helper that maps
      `local_date`/`local_time`/`duration_minutes` + user timezone → `start_at`/`due_at`;
      apply in the auto-confirm block of `run_pipeline` (`backend/app/modules/voice/service.py`).
- [x] T003 Frontend: make `TodayPage` use `VoiceRecorder` as the primary voice entry
      (`frontend/src/modules/today/TodayPage.vue`); poll path already handles statuses.
- [x] T004 Verify audio format: record webm → SiliconFlow transcribe; if rejected, record
      wav client-side or transcode. Decide + implement the minimal option.
- [x] T005 Tests: extend `tests/integration/test_voice_pipeline.py` to assert `start_at`/
      `due_at` are set from a dated candidate.
- [x] T006 Deploy to master; verify with a real Chinese recording (transcript + calendar).

## Increment 2 — multiple tasks per message

- [x] T007 Add `VoiceTasksV1` strict model (`backend/app/services/llm/schemas.py`) and
      checked-in contract `contracts/schemas/voice-tasks.v1.json`; update schema-drift test.
- [x] T008 Update parse system prompt to split a message into independent tasks; switch
      `run_pipeline` to request the list schema and loop task creation (reusing T002 helper).
- [x] T009 Persist the list in `parsed_payload_json`; create one `EntityRelation` per task.
- [x] T010 Tests: multi-item transcript → N tasks with per-item dates.
- [x] T011 Deploy to master; verify with a multi-item Chinese recording.

## Notes

- Constitution II deviation (auto-create instead of confirm) is recorded in spec.md;
  reversibility (edit/delete) is the mitigation.
- Habits/collections routing intentionally out of scope.
