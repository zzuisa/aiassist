import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { agentConversationsApi } from '@/api/agentConversations'
import { useAgentConversationsStore } from '@/stores/agentConversations'

describe('Agent conversation session', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('creates a fresh conversation for the first message without loading history', async () => {
    const list = vi.spyOn(agentConversationsApi, 'listConversations')
    vi.spyOn(agentConversationsApi, 'createConversation').mockResolvedValue({
      id: 'conversation-new',
      title: null,
      status: 'active',
      last_message_at: null,
      created_at: '2026-08-19T00:00:00Z',
    })
    vi.spyOn(agentConversationsApi, 'submitMessage').mockResolvedValue({
      message: {
        id: 'message-new',
        role: 'user',
        kind: 'text',
        content: { text: '开始新任务' },
        turn_id: 'turn-new',
        created_at: '2026-08-19T00:00:00Z',
      },
      turn: {
        id: 'turn-new',
        conversation_id: 'conversation-new',
        status: 'accepted',
        route_kind: null,
        current_step: null,
        agent_task_id: null,
        error_message: null,
        created_at: '2026-08-19T00:00:00Z',
        finished_at: null,
      },
    })

    const store = useAgentConversationsStore()
    await store.sendMessage('开始新任务')

    expect(agentConversationsApi.createConversation).toHaveBeenCalledOnce()
    expect(list).not.toHaveBeenCalled()
    expect(store.conversationId).toBe('conversation-new')
    expect(store.messages.map((message) => message.id)).toEqual(['message-new'])
    store.reset()
  })
})
