import { api } from '@/api/client'
import type { Task } from '@/api/tasks'

// A planned task candidate (mirrors the backend VoiceTaskV1 shape we round-trip).
export interface PlanTask {
  title: string
  content_type: string
  description: string | null
  local_date: string | null
  local_time: string | null
  timezone: string
  duration_minutes: number | null
  priority: number
  important: boolean
  reminder: unknown | null
  recurring: boolean
  recurrence_rule: string | null
  original_text: string
}

export interface PlanResult {
  tasks: PlanTask[]
  questions: string[]
  summary: string
  error: string | null
}

export interface QA {
  question: string
  answer: string
}

export const planApi = {
  analyze: (text: string, answers: QA[] = []) =>
    api.post<PlanResult>('/tasks/analyze', { text, answers }),
  commit: (tasks: PlanTask[]) => api.post<{ created: Task[] }>('/tasks/plan/commit', { tasks }),
}
