import { calendarApi } from '@/api/calendar'
import type { Task } from '@/api/tasks'
import { ApiError } from '@/api/client'

export interface RescheduleOutcome {
  ok: boolean
  task?: Task
  reason?: 'version_conflict' | 'fixed_event' | 'error'
}

// Persist a drag/resize. On failure the caller MUST revert the calendar view.
// Fixed events never reach here because the calendar disables them, but the
// backend is the final authority and we surface its rejection.
export async function persistReschedule(
  task: Task,
  startAt: string | null,
  dueAt: string | null,
): Promise<RescheduleOutcome> {
  try {
    const updated = await calendarApi.reschedule(task.id, task.version, startAt, dueAt)
    return { ok: true, task: updated }
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.code === 'version_conflict') return { ok: false, reason: 'version_conflict' }
      if (err.code === 'fixed_event') return { ok: false, reason: 'fixed_event' }
    }
    return { ok: false, reason: 'error' }
  }
}
