<script setup lang="ts">
import { ref } from 'vue'
import type { AgentMessage } from '@/api/agentConversations'
import ConversationTimeline from '@/components/agent/ConversationTimeline.vue'

export interface ConversationPanelMessage extends AgentMessage {
  pending?: boolean
}

const props = defineProps<{
  messages: ConversationPanelMessage[]
  loading: boolean
  sending: boolean
  error: string
}>()

const emit = defineEmits<{ send: [text: string] }>()

const draft = ref('')

function submit(): void {
  const value = draft.value.trim()
  if (!value || props.sending) return
  emit('send', value)
  draft.value = ''
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
  }
}
</script>

<template>
  <section
    class="conversation-panel"
    aria-label="对话"
  >
    <div
      class="messages"
      role="log"
      aria-live="polite"
    >
      <p
        v-if="loading"
        class="state-message"
        role="status"
      >
        正在加载会话…
      </p>
      <p
        v-else-if="!messages.length"
        class="state-message"
      >
        跟我打个招呼，或者直接说说你想做什么。
      </p>
      <ConversationTimeline
        v-else
        :messages="messages"
      />
    </div>

    <p
      v-if="error"
      class="error-banner"
      role="alert"
    >
      {{ error }}
    </p>

    <form
      class="composer"
      @submit.prevent="submit"
    >
      <label
        for="conversation-input"
        class="sr-only"
      >跟我说点什么</label>
      <textarea
        id="conversation-input"
        v-model="draft"
        rows="1"
        maxlength="4000"
        placeholder="输入消息，按 Enter 发送"
        :disabled="sending"
        @keydown="onKeydown"
      />
      <button
        type="submit"
        :disabled="sending || !draft.trim()"
      >
        {{ sending ? '发送中…' : '发送' }}
      </button>
    </form>
  </section>
</template>

<style scoped>
.conversation-panel {
  display: grid;
  gap: var(--space-3);
}
.messages {
  display: grid;
  gap: var(--space-2);
  min-height: 4rem;
}
.state-message {
  color: var(--color-text-muted);
}
.message {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  max-width: 80%;
  justify-self: start;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}
.message.role-user {
  justify-self: end;
  background: var(--color-surface-2);
}
.message.pending {
  opacity: 0.7;
}
.message.error {
  border-color: var(--status-overdue);
  color: var(--status-overdue);
}
.message.role-assistant:has(small) {
  border-inline-start: 3px solid var(--color-primary);
}
.composer {
  display: flex;
  gap: var(--space-2);
  align-items: flex-end;
}
textarea {
  flex: 1;
  resize: vertical;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
}
button {
  min-height: var(--tap-target);
}
.error-banner {
  color: var(--status-overdue);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
</style>
