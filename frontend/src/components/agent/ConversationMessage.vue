<script setup lang="ts">
import { computed } from 'vue'
import { messageText, type AgentMessage } from '@/api/agentConversations'

const props = defineProps<{ message: AgentMessage & { pending?: boolean } }>()
const text = computed(() => messageText(props.message))
const timestamp = computed(() => new Date(props.message.created_at).toLocaleString())
</script>

<template>
  <article
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
</style>
