<script setup lang="ts">
import type { ActionCard } from '@/api/assistant'

// Structured action card: grounded reasoning + explicit action buttons. Actions
// take effect only when the user clicks them; there is no implicit chat action.
defineProps<{ card: ActionCard; applying: string | null }>()
defineEmits<{ (e: 'apply', actionId: string): void }>()
</script>

<template>
  <article
    class="card"
    :class="`kind-${card.kind}`"
  >
    <h3>{{ card.title }}</h3>

    <p
      v-if="card.body.reason"
      class="reason"
    >
      {{ card.body.reason }}
    </p>
    <p
      v-if="card.body.message"
      class="message"
    >
      {{ card.body.message }}
    </p>

    <p
      v-if="Array.isArray(card.body.fixed_kept) && card.body.fixed_kept.length"
      class="fixed"
    >
      固定事件保持不变（{{ (card.body.fixed_kept as string[]).length }} 项）。
    </p>

    <div
      v-if="card.actions.length"
      class="actions"
    >
      <button
        v-for="action in card.actions"
        :key="action.id"
        type="button"
        :class="{ destructive: action.destructive }"
        :disabled="applying === action.id"
        @click="$emit('apply', action.id)"
      >
        {{ applying === action.id ? '应用中…' : action.label }}
      </button>
    </div>
    <p
      v-else
      class="no-actions"
    >
      此结果没有可执行的操作。
    </p>
  </article>
</template>

<style scoped>
.card {
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--status-ai);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}
.kind-summary {
  border-left-color: var(--status-muted);
}
h3 {
  margin: 0 0 var(--space-2);
}
.reason,
.message {
  color: var(--color-text-muted);
}
.fixed {
  color: var(--status-muted);
  font-size: 0.85rem;
}
.actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
.actions button {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: 1px solid var(--status-ai);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--status-ai);
  cursor: pointer;
  text-align: left;
}
.actions button.destructive {
  border-color: var(--status-urgent);
  color: var(--status-urgent);
}
.actions button:disabled {
  opacity: 0.6;
}
.no-actions {
  color: var(--color-text-muted);
  font-size: 0.85rem;
  margin-top: var(--space-2);
}
</style>
