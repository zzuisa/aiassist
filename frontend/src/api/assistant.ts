import { api } from '@/api/client'

export interface ActionCardAction {
  id: string
  label: string
  destructive?: boolean
}

export interface ActionCard {
  id: string
  kind: 'plan' | 'task' | 'search_results' | 'habit_analysis' | 'blog_draft' | 'summary'
  title: string
  body: Record<string, unknown>
  actions: ActionCardAction[]
}

export interface EntityRef {
  type: string
  id: string
  version?: number
}

export interface AssistantRun {
  id: string
  intent: string
  status: string
  job_id?: string
  cards: ActionCard[]
  grounded_refs: EntityRef[]
}

export const assistantApi = {
  run: (intent: string, instruction?: string) =>
    api.post<AssistantRun>('/assistant/runs', { intent, instruction }),
  get: (runId: string) => api.get<AssistantRun>(`/assistant/runs/${runId}`),
  action: (runId: string, actionId: string) =>
    api.post<{ applied: string }>(`/assistant/runs/${runId}/actions/${actionId}`),
}

export const INTENTS = [
  { value: 'plan_today', label: '安排今天' },
  { value: 'adjust_week', label: '调整本周' },
  { value: 'summarize_day', label: '总结今天' },
]
