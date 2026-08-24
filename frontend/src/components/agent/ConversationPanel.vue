<script setup lang="ts">
import { ref } from 'vue'
import type { AgentMessage } from '@/api/agentConversations'
import ConversationTimeline from '@/components/agent/ConversationTimeline.vue'
import type { AgentPlan } from '@/api/agentPlans'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseTextarea from '@/components/base/BaseTextarea.vue'

export interface ConversationPanelMessage extends AgentMessage {
  pending?: boolean
}

const props = withDefaults(defineProps<{
  messages: ConversationPanelMessage[]
  loading?: boolean
  sending: boolean
  error: string
  plans?: AgentPlan[]
  retryingPlanId?: string | null
}>(), {
  loading: false,
  plans: () => [],
  retryingPlanId: null,
})

const emit = defineEmits<{
  send: [text: string]
  retryPlan: [planId: string]
}>()

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
        开始一次新对话：直接说说你想查询或处理什么。
      </p>
      <template v-else>
        <ConversationTimeline
          :messages="messages"
          :plans="plans"
          :retrying-plan-id="retryingPlanId"
          @retry-plan="emit('retryPlan', $event)"
        />
      </template>
    </div>

    <slot name="status" />

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
      <BaseTextarea
        id="conversation-input"
        v-model="draft"
        rows="1"
        maxlength="4000"
        placeholder="输入消息，按 Enter 发送"
        :disabled="sending"
        @keydown="onKeydown"
      />
      <BaseButton
        type="submit"
        variant="primary"
        :disabled="sending || !draft.trim()"
      >
        {{ sending ? '发送中…' : '发送' }}
      </BaseButton>
    </form>
  </section>
</template>

<style scoped>
.conversation-panel {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-6);
}
.messages {
  display: grid;
  gap: var(--space-3);
  min-height: 12rem;
  max-height: min(54vh, 620px);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--space-2);
  scrollbar-color: var(--color-scrollbar) transparent;
}
.state-message {
  display: grid;
  min-height: 10rem;
  margin: 0;
  place-items: center;
  color: var(--color-text-muted);
  text-align: center;
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
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-composer);
}
.composer :deep(.base-textarea) {
  flex: 1;
  min-width: 0;
}
.composer :deep(textarea) {
  max-height: 12rem;
}
.error-banner {
  margin: 0;
  padding: var(--space-3);
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-sm);
  background: var(--status-danger-soft);
  color: var(--status-overdue);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}

@media (max-width: 700px) {
  .conversation-panel {
    padding: var(--space-4);
  }

  .messages {
    max-height: 52vh;
    min-height: 15rem;
    padding: 0;
  }

  .composer {
    position: sticky;
    bottom: var(--space-2);
    z-index: 2;
    padding: var(--space-2) calc(var(--space-2) + var(--mobile-nav-clearance)) var(--space-2) var(--space-2);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-composer);
  }
}
</style>
