import { api } from '@/api/client'

export type AgentTaskStatus =
  | 'pending'
  | 'running'
  | 'waiting_confirmation'
  | 'success'
  | 'partial_success'
  | 'failed'

export interface AgentRun {
  agent_id: string
  parent_agent_id: string | null
  agent_key: string
  agent_version: string
  agent_name: string
  responsibility: string
  current_task: string
  status: AgentTaskStatus | 'skipped'
  current_tool: string | null
  allow_write: boolean
  progress: { current: number; total: number; stage_label: string | null } | null
  result_summary: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
}

export interface AgentTask {
  task_id: string
  job_id: string
  request_text: string
  intent_key: string
  status: AgentTaskStatus
  result_summary: string | null
  created_at: string
  finished_at: string | null
}

export interface AgentTaskDetail extends AgentTask {
  runs: AgentRun[]
}

export type ConfirmationDecision = 'approve' | 'reject'

export interface PendingWriteTarget {
  id: string
  version: number | null
}

export interface PendingWrite {
  confirmation_id: string
  operation_type: 'create' | 'update' | 'delete' | 'publish' | 'rollback'
  target_type: string
  targets: PendingWriteTarget[]
  preview: Record<string, unknown>
  affected_count: number
  reversible: boolean
  high_risk: boolean
  decision: 'pending' | 'approved' | 'rejected' | 'expired'
  decided_at: string | null
  created_at: string
}

export interface AgentArticleResult {
  id: string
  title: string
  link: string
  category: string | null
  tags: string[]
  published_at: string | null
  updated_at: string | null
  status: string
}

export interface AgentReply {
  处理结果: AgentArticleResult[] | Record<string, unknown> | string
  执行记录: Array<Record<string, unknown>>
  局限说明?: Record<string, unknown>
}

export const agentApi = {
  createTask: (requestText: string, previousTaskId?: string) =>
    api.post<AgentTask>('/agent/tasks', {
      request_text: requestText,
      previous_task_id: previousTaskId,
    }),
  listTasks: (limit = 20, status?: AgentTaskStatus) =>
    api.get<AgentTask[]>('/agent/tasks', { limit, status }),
  getTask: (taskId: string) => api.get<AgentTaskDetail>(`/agent/tasks/${taskId}`),
  listConfirmations: (taskId: string) =>
    api.get<PendingWrite[]>(`/agent/tasks/${taskId}/confirmations`),
  decideConfirmation: (
    taskId: string,
    confirmationId: string,
    decision: ConfirmationDecision,
  ) =>
    api.post<PendingWrite>(
      `/agent/tasks/${taskId}/confirmations/${confirmationId}`,
      { decision },
    ),
}

export function parseAgentReply(summary: string | null): AgentReply | null {
  if (!summary) return null
  try {
    return JSON.parse(summary) as AgentReply
  } catch {
    return null
  }
}
