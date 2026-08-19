import { api } from '@/api/client'

export type AgentPlanStatus =
  | 'planning'
  | 'pending'
  | 'running'
  | 'waiting_user'
  | 'success'
  | 'partial_success'
  | 'failed'
  | 'stalled'
  | 'cancelled'

export type AgentPlanStepStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'waiting_confirmation'
  | 'success'
  | 'partial_success'
  | 'failed'
  | 'blocked'
  | 'skipped'
  | 'stalled'
  | 'cancelled'

export interface AgentPlanError {
  code: string
  message: string
  retryable: boolean
}

export interface AgentPlanStep {
  step_id: string
  step_key: string
  position: number
  title: string
  responsibility: string
  agent: { key: string; name: string }
  tool_name: string
  operation_type: string
  depends_on: string[]
  status: AgentPlanStepStatus
  progress: { current: number; total: number; stage_label: string | null } | null
  attempt_count: number
  stage_label: string | null
  result_summary: string | null
  error: AgentPlanError | null
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
}

export interface AgentPlan {
  schema_version: 'agent-plan-view.v1'
  plan_id: string
  turn_id: string | null
  task_id: string
  user_message_id: string | null
  objective: string
  status: AgentPlanStatus
  version: number
  counts: { total: number; completed: number; failed: number; skipped: number }
  elapsed_ms: number | null
  result_summary: string | null
  error: AgentPlanError | null
  steps: AgentPlanStep[]
  created_at: string
  finished_at: string | null
}

export const PLAN_TERMINAL_STATUSES: readonly AgentPlanStatus[] = [
  'success',
  'partial_success',
  'failed',
  'stalled',
  'cancelled',
]

export const agentPlansApi = {
  listConversationPlans: (conversationId: string, limit = 20) =>
    api.get<AgentPlan[]>(`/agent/conversations/${conversationId}/plans`, { limit }),
  getPlan: (planId: string) => api.get<AgentPlan>(`/agent/plans/${planId}`),
  getTurnPlan: (turnId: string) => api.get<AgentPlan>(`/agent/turns/${turnId}/plan`),
  retryPlan: (planId: string) =>
    api.post<AgentPlan>(`/agent/plans/${planId}/retry`, { mode: 'failed_chain' }),
}
