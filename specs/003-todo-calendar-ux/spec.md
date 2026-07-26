# Feature Specification: Todo ↔ Calendar UX + job hygiene

**Feature dir**: `specs/003-todo-calendar-ux` · **Branch**: master · **Created**: 2026-07-26

## Summary

Four operator-requested improvements after the voice-inbox work landed:

1. **Stale background tasks** — every load showed ~7 "等待确认" voice jobs. These
   are orphaned `voice.transcribe` jobs left in `waiting_user` by the pre-auto-confirm
   flow (their records already reached confirmed/failed). Retire them and prevent
   recurrence.
2. **Todo ↔ calendar real-time sync** — a change in one view (complete, reschedule,
   add-to-calendar) must be reflected in the other without a manual reload.
3. **Left-swipe a todo → "添加到日历"** — quick action to give an undated todo a
   concrete calendar slot.
4. **Mobile interaction polish** — stronger drag/tap feedback, and calendar drags
   apply optimistically on the client first, are cached, and sync to the backend in
   a debounced batch (better UX under rapid edits).

## Requirements

- **FR-001**: A maintenance job MUST reconcile orphaned `voice.transcribe` jobs to
  their record's real outcome, and cancel any non-terminal job idle >24h. It runs on
  Celery Beat and is idempotent. Existing orphans are cleaned once on rollout.
- **FR-002**: Task mutations from any view MUST bump a shared signal; the Today list
  and the calendar refetch on that signal and on tab focus.
- **FR-003**: A todo card MUST support a left-swipe revealing "添加到日历"; activating
  it schedules the task (next full hour today, else tomorrow 09:00, 30 min) and it
  appears on the calendar via FR-002.
- **FR-004**: Calendar drag/resize MUST update the view immediately, queue the change
  locally, and flush to the backend after a short idle (debounced) or when the tab is
  hidden / the page unmounts. Failed items revert and the view resyncs.
- **FR-005**: Drag and tap MUST have visible feedback (event lift while dragging, card
  press scale), honoring `prefers-reduced-motion`.

## Data Safety & AI Control

- Principle I (durable capture): queued calendar moves flush on idle, on tab-hide, and
  on unmount, with a short (1.5s) idle window, so a reschedule is not lost. A failed
  flush reverts the on-screen position and resyncs from the server (server is truth).
- No AI behavior changed. Fixed events remain non-movable (backend authority).

## Success Criteria

- **SC-001**: A fresh load shows no stale "等待确认" jobs.
- **SC-002**: Completing/rescheduling a task in one view updates the other without reload.
- **SC-003**: Swiping a todo and tapping "添加到日历" places it on the calendar.
- **SC-004**: Rapid calendar drags feel instant; the backend receives one batched sync.

## Notes

Batch sync reuses the existing per-task reschedule endpoint (parallel calls on flush);
no new backend batch endpoint was added to keep surface minimal.
