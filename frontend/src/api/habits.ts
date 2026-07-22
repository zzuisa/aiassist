import { api } from '@/api/client'

export interface Habit {
  id: string
  name: string
  description?: string | null
  recurrence_rule: string
  suggested_time_local?: string | null
  target_minutes?: number | null
  minimum_amount?: number | null
  unit?: string | null
  priority: number
  auto_create_task: boolean
  is_ai_adjustable: boolean
  status: string
  version: number
}

export interface HabitLog {
  id: string
  habit_id: string
  local_date: string
  status: 'completed' | 'partial' | 'skipped'
  amount?: number | null
  duration_seconds?: number | null
  skip_reason?: string | null
  skip_note?: string | null
}

export interface HabitStats {
  streak: number
  completion_rate: number
  total_logs: number
  completed_logs: number
  heatmap: Record<string, Record<string, number>>
}

export type SkipReason =
  | 'no_time'
  | 'too_tired'
  | 'forgot'
  | 'unrealistic_plan'
  | 'not_suitable'
  | 'other'

export const habitsApi = {
  list: () => api.get<Habit[]>('/habits'),
  create: (body: Partial<Habit>) => api.post<Habit>('/habits', body),
  checkIn: (id: string, localDate: string, status: 'completed' | 'partial', durationSeconds?: number) =>
    api.post<HabitLog>(`/habits/${id}/check-ins`, {
      local_date: localDate,
      status,
      duration_seconds: durationSeconds,
    }),
  skip: (id: string, localDate: string, reason: SkipReason, note?: string) =>
    api.post<HabitLog>(`/habits/${id}/skip`, { local_date: localDate, reason, note }),
  stats: (from: string, to: string) => api.get<HabitStats>('/habits/stats', { from, to }),
}
