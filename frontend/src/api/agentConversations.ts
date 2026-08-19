import { api } from '@/api/client'

export type ConversationStatus = 'active' | 'archived'

export type MessageRole = 'user' | 'assistant' | 'system'
export type MessageKind = 'text' | 'clarification' | 'result' | 'error'

export type TurnStatus =
  | 'accepted'
  | 'routing'
  | 'waiting_clarification'
  | 'executing'
  | 'waiting_confirmation'
  | 'success'
  | 'partial_success'
  | 'failed'
  | 'stalled'
  | 'cancelled'

export const TURN_TERMINAL_STATUSES: readonly TurnStatus[] = [
  'success',
  'partial_success',
  'failed',
  'stalled',
  'cancelled',
]

export interface Conversation {
  id: string
  title: string | null
  status: ConversationStatus
  last_message_at: string | null
  created_at: string
}

export interface Turn {
  id: string
  conversation_id: string
  status: TurnStatus
  route_kind: string | null
  current_step: string | null
  agent_task_id: string | null
  error_message: string | null
  created_at: string
  finished_at: string | null
}

export interface ConversationDetail extends Conversation {
  active_turns: Turn[]
}

export interface AgentMessage {
  id: string
  role: MessageRole
  kind: MessageKind
  content: Record<string, unknown>
  turn_id: string | null
  created_at: string
}

export interface MessagePage {
  items: AgentMessage[]
  next_cursor: string | null
}

export interface TurnAccepted {
  message: AgentMessage
  turn: Turn
}

/**
 * A client-generated idempotency key. Retried delivery of the same submit
 * (e.g. after a dropped response) with the same id returns the SAME turn
 * instead of creating a duplicate message — see conversation_service.accept_message.
 */
export function newClientMessageId(): string {
  return crypto.randomUUID()
}

export const agentConversationsApi = {
  createConversation: () => api.post<Conversation>('/agent/conversations'),
  listConversations: (limit = 50, status?: ConversationStatus) =>
    api.get<Conversation[]>('/agent/conversations', { limit, status }),
  getConversation: (conversationId: string) =>
    api.get<ConversationDetail>(`/agent/conversations/${conversationId}`),
  getTurn: (turnId: string) => api.get<Turn>(`/agent/turns/${turnId}`),
  retryTurn: (turnId: string) => api.post<TurnAccepted>(`/agent/turns/${turnId}/retry`),
  submitMessage: (conversationId: string, text: string, clientMessageId = newClientMessageId()) =>
    api.post<TurnAccepted>(`/agent/conversations/${conversationId}/messages`, {
      client_message_id: clientMessageId,
      text,
    }),
  listMessages: (conversationId: string, cursor?: string | null, limit = 50) =>
    api.get<MessagePage>(`/agent/conversations/${conversationId}/messages`, {
      cursor: cursor ?? undefined,
      limit,
    }),
  listRecentMessages: (conversationId: string, before?: string | null, limit = 12) =>
    api.get<MessagePage>(`/agent/conversations/${conversationId}/messages`, {
      latest: true,
      before: before ?? undefined,
      limit,
    }),
}

export function messageText(message: AgentMessage): string {
  const text = message.content?.text
  return typeof text === 'string' ? text : ''
}
