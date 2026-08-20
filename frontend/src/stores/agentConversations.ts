import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  agentConversationsApi,
  newClientMessageId,
  TURN_TERMINAL_STATUSES,
  type AgentMessage,
  type Turn,
} from '@/api/agentConversations'
import { agentPlansApi, type AgentPlan } from '@/api/agentPlans'

const LOCAL_ID_PREFIX = 'local-'

export interface ConversationMessageView extends AgentMessage {
  /** True only for an optimistically-inserted message awaiting the server echo. */
  pending?: boolean
}

function isServerId(id: string | null): id is string {
  return !!id && !id.startsWith(LOCAL_ID_PREFIX)
}

export const useAgentConversationsStore = defineStore('agentConversations', () => {
  const conversationId = ref<string | null>(null)
  const messages = ref<ConversationMessageView[]>([])
  const activeTurns = ref<Turn[]>([])
  const plans = ref<AgentPlan[]>([])
  const sending = ref(false)
  const error = ref('')
  async function ensureConversation(): Promise<string> {
    if (conversationId.value) return conversationId.value
    const conversation = await agentConversationsApi.createConversation()
    conversationId.value = conversation.id
    return conversation.id
  }

  function startFreshConversation(): void {
    conversationId.value = null
    messages.value = []
    activeTurns.value = []
    plans.value = []
    error.value = ''
  }

  async function poll(): Promise<void> {
    const id = conversationId.value
    if (!id) return
    try {
      const lastMessage = messages.value[messages.value.length - 1]
      const cursor = lastMessage && isServerId(lastMessage.id) ? lastMessage.id : null
      const [page, detail, planItems] = await Promise.all([
        agentConversationsApi.listMessages(id, cursor),
        agentConversationsApi.getConversation(id),
        agentPlansApi.listConversationPlans(id),
      ])
      if (page.items.length) {
        messages.value = [...messages.value, ...page.items]
      }
      activeTurns.value = detail.active_turns
      for (const plan of planItems) applyPlan(plan)
    } catch {
      // Best-effort refresh; the user can still send another message.
    }
  }

  function applyConversationSnapshot(items: Array<Record<string, unknown>>): void {
    if (!conversationId.value) return
    activeTurns.value = items
      .filter((item) => item.conversation_id === conversationId.value)
      .map((item) => item as unknown as Turn)
  }

  function applyPlanSnapshot(items: Array<Record<string, unknown>>): void {
    if (!conversationId.value) return
    for (const item of items) applyPlan(item as unknown as AgentPlan)
  }

  function applyPlan(plan: AgentPlan): void {
    if (!plan.turn_id) return
    const turn = activeTurns.value.find((item) => item.id === plan.turn_id)
    const belongsToConversation = turn?.conversation_id === conversationId.value
      || messages.value.some((message) => message.id === plan.user_message_id)
    if (!belongsToConversation) return
    const existing = plans.value.find((item) => item.plan_id === plan.plan_id)
    if (existing && existing.version >= plan.version) return
    plans.value = [
      ...plans.value.filter((item) => item.plan_id !== plan.plan_id),
      plan,
    ].sort((left, right) => left.created_at.localeCompare(right.created_at))
  }

  function applyPlanEvent(data: Record<string, unknown>): void {
    if (data.event_type !== 'agent.plan_updated') return
    const plan = data.plan
    if (plan && typeof plan === 'object') applyPlan(plan as AgentPlan)
  }

  function applyConversationEvent(data: Record<string, unknown>): void {
    if (!conversationId.value || data.conversation_id !== conversationId.value) return
    const turnId = data.turn_id
    const status = data.status as Turn['status']
    if (typeof turnId === 'string') {
      if (['success', 'partial_success', 'cancelled'].includes(status)) {
        activeTurns.value = activeTurns.value.filter((turn) => turn.id !== turnId)
      } else {
        const existing = activeTurns.value.find((turn) => turn.id === turnId)
        activeTurns.value = [
          ...activeTurns.value.filter((turn) => turn.id !== turnId),
          {
            ...(existing ?? ({ id: turnId, conversation_id: conversationId.value } as Turn)),
            status,
            current_step: (data.stage_label as string | null) ?? null,
          },
        ]
      }
    }
    if (data.event_type === 'conversation.message_created') void poll()
  }

  async function sendMessage(text: string): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed || sending.value) return
    error.value = ''
    const clientMessageId = newClientMessageId()
    const optimisticId = `${LOCAL_ID_PREFIX}${clientMessageId}`
    const optimistic: ConversationMessageView = {
      id: optimisticId,
      role: 'user',
      kind: 'text',
      content: { text: trimmed },
      turn_id: null,
      created_at: new Date().toISOString(),
      pending: true,
    }
    messages.value = [...messages.value, optimistic]
    // Enter the visible thinking state synchronously.  Creating a first
    // conversation is a network request too, so waiting for it before setting
    // ``sending`` left a user-visible silent gap after pressing Enter.
    sending.value = true
    let id: string
    try {
      id = await ensureConversation()
    } catch {
      messages.value = messages.value.map((message) =>
        message.id === optimisticId ? { ...message, pending: false, kind: 'error' } : message,
      )
      error.value = '无法开始会话，请稍后重试。'
      sending.value = false
      return
    }
    try {
      const accepted = await agentConversationsApi.submitMessage(id, trimmed, clientMessageId)
      messages.value = messages.value.map((message) =>
        message.id === optimisticId ? { ...accepted.message, pending: false } : message,
      )
      const isActive = !TURN_TERMINAL_STATUSES.includes(accepted.turn.status)
      activeTurns.value = [
        ...activeTurns.value.filter((turn) => turn.id !== accepted.turn.id),
        ...(isActive ? [accepted.turn] : []),
      ]
      void poll()
    } catch {
      messages.value = messages.value.map((message) =>
        message.id === optimisticId ? { ...message, pending: false, kind: 'error' } : message,
      )
      error.value = '消息发送失败，请重试。'
    } finally {
      sending.value = false
    }
  }

  async function retryTurn(turnId: string): Promise<void> {
    error.value = ''
    try {
      const accepted = await agentConversationsApi.retryTurn(turnId)
      activeTurns.value = [
        ...activeTurns.value.filter((turn) => turn.id !== accepted.turn.id),
        accepted.turn,
      ]
      void poll()
    } catch {
      error.value = '无法重试这条消息，请刷新后再试。'
    }
  }

  async function retryPlan(planId: string): Promise<void> {
    error.value = ''
    try {
      applyPlan(await agentPlansApi.retryPlan(planId))
    } catch {
      error.value = '无法重试这个执行计划，请刷新后再试。'
    }
  }

  function reset(): void {
    startFreshConversation()
  }

  return {
    conversationId,
    messages,
    activeTurns,
    plans,
    sending,
    error,
    startFreshConversation,
    sendMessage,
    retryTurn,
    applyConversationEvent,
    applyConversationSnapshot,
    applyPlanSnapshot,
    applyPlanEvent,
    retryPlan,
    reset,
  }
})
