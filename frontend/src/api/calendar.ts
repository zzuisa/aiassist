import { api } from '@/api/client'
import type { Task } from '@/api/tasks'
import type { AsyncJob } from '@/api/types'

export type { Task } from '@/api/tasks'

export interface Conflict {
  task_id: string
  conflicting_task_id: string
  overlap_minutes: number
  fixed: boolean
}

export interface WeekCalendar {
  starts_on: string
  events: Task[]
  unscheduled: Task[]
  conflicts: Conflict[]
}

export interface ScheduleSuggestion {
  suggestion_id: string
  task_id: string
  task_version: number
  recommendation: 'move' | 'defer' | 'split' | 'keep'
  old_start: string | null
  old_end: string | null
  new_start: string | null
  new_end: string | null
  reason: string
  conflicting_task_ids: string[]
  selectable: boolean
}

export interface SchedulePreview {
  id: string
  status: string
  suggestions: ScheduleSuggestion[]
  explanation: string | null
  expires_at: string
}

export interface ApplyResult {
  applied: string[]
  rejected: Array<{ suggestion_id: string; code: string; detail: string }>
  activity_id: string
}

export const calendarApi = {
  week: (startsOn: string) => api.get<WeekCalendar>('/calendar/week', { starts_on: startsOn }),
  reschedule: (id: string, version: number, startAt: string | null, dueAt: string | null) =>
    api.post<Task>(`/tasks/${id}/reschedule`, { version, start_at: startAt, due_at: dueAt }),
  createPreview: (scopeStart: string, scopeEnd: string) =>
    api.post<{ preview_id: string; job: AsyncJob }>('/schedule-previews', {
      scope_start: scopeStart,
      scope_end: scopeEnd,
    }),
  getPreview: (id: string) => api.get<SchedulePreview>(`/schedule-previews/${id}`),
  applyPreview: (id: string, suggestionIds: string[]) =>
    api.post<ApplyResult>(`/schedule-previews/${id}/apply`, { suggestion_ids: suggestionIds }),
}
