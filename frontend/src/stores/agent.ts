import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export type AgentLiveStatus =
  | 'pending'
  | 'running'
  | 'waiting_confirmation'
  | 'success'
  | 'partial_success'
  | 'failed'
  | 'skipped'

export interface AgentLiveProgress {
  current: number
  total: number
  stage_label: string | null
}

export interface AgentLiveRun {
  agent_id: string
  parent_agent_id: string | null
  agent_key: string
  agent_version: string
  agent_name: string
  responsibility: string
  current_task: string
  status: AgentLiveStatus
  current_tool: string | null
  progress: AgentLiveProgress | null
  result_summary: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  task_id: string
  job_id: string
  timestamp: string
}

interface AgentStatusEnvelope {
  task_id: string
  job_id: string
  timestamp: string
  agent: Omit<AgentLiveRun, 'task_id' | 'job_id' | 'timestamp'>
}

export const useAgentStore = defineStore('agent', () => {
  const agents = ref<Map<string, AgentLiveRun>>(new Map())

  const activeAgents = computed(() =>
    [...agents.value.values()].filter((agent) =>
      ['pending', 'running', 'waiting_confirmation'].includes(agent.status),
    ),
  )

  function applyStatusEvent(data: Record<string, unknown>): void {
    const envelope = data as unknown as AgentStatusEnvelope
    if (!envelope.task_id || !envelope.job_id || !envelope.agent?.agent_id) return
    const incomingTimestamp = envelope.timestamp ?? ''
    const current = agents.value.get(envelope.agent.agent_id)
    if (current && current.timestamp > incomingTimestamp) return
    agents.value.set(envelope.agent.agent_id, {
      ...envelope.agent,
      task_id: envelope.task_id,
      job_id: envelope.job_id,
      timestamp: incomingTimestamp,
    })
  }

  function applySnapshot(data: Record<string, unknown>): void {
    const snapshot = (data.agents as Array<Record<string, unknown>>) ?? []
    for (const item of snapshot) applyStatusEvent(item)
  }

  function forTask(taskId: string): AgentLiveRun[] {
    return [...agents.value.values()].filter((agent) => agent.task_id === taskId)
  }

  function clear(): void {
    agents.value.clear()
  }

  return { agents, activeAgents, applyStatusEvent, applySnapshot, forTask, clear }
})
