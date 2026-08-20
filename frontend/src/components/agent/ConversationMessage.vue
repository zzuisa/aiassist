<script setup lang="ts">
import { computed } from 'vue'
import { messageText, type AgentMessage } from '@/api/agentConversations'
import AgentResultList from './AgentResultList.vue'
import { parseResultText, presentAgentResult } from './resultPresentation'

const props = defineProps<{ message: AgentMessage & { pending?: boolean } }>()
const text = computed(() => messageText(props.message))
const timestamp = computed(() => new Date(props.message.created_at).toLocaleString())
const structuredResult = computed(() => parseResultText(text.value))
const presentedResult = computed(() => presentAgentResult(structuredResult.value))
const resultPreview = computed(() => {
  if (presentedResult.value.summary) return presentedResult.value.summary
  const compact = text.value.replace(/\s+/g, ' ').trim()
  return compact.length > 88 ? `${compact.slice(0, 88)}…` : compact
})
</script>

<template>
  <details
    v-if="message.kind === 'result'"
    class="message result-message"
    :class="`role-${message.role}`"
  >
    <summary>
      <strong>处理结果</strong>
      <span v-if="resultPreview">{{ resultPreview }}</span>
    </summary>
    <AgentResultList
      v-if="structuredResult && presentedResult.items.length"
      :items="presentedResult.items"
      :summary="presentedResult.summary"
    />
    <p v-else>
      {{ text }}
    </p>
    <time :datetime="message.created_at">{{ timestamp }}</time>
  </details>
  <article
    v-else
    class="message"
    :class="[`role-${message.role}`, { pending: message.pending, error: message.kind === 'error' }]"
  >
    <p>{{ text }}</p>
    <time :datetime="message.created_at">{{ timestamp }}</time>
    <small v-if="message.pending">发送中…</small>
  </article>
</template>

<style scoped>
.message { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-sm); max-width: 80%; }
.role-user { justify-self: end; background: var(--color-surface-2); }
.pending { opacity: .7; }
.error { color: var(--status-overdue); }
time { display: block; color: var(--color-text-muted); font-size: .75rem; }
.result-message { width: min(100%, 38rem); }
.result-message summary { cursor: pointer; display: grid; gap: .2rem; }
.result-message summary span { color: var(--color-text-muted); font-weight: 400; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.result-message p { max-height: 16rem; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
