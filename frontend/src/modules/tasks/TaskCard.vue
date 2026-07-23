<script setup lang="ts">
import { computed } from 'vue'
import type { Task } from '@/api/tasks'

const props = defineProps<{ task: Task }>()
defineEmits<{ (e: 'complete', task: Task): void; (e: 'open', task: Task): void }>()

// Status is conveyed by both a colored dot AND a text label (never color alone).
const statusLabel = computed(() => {
  if (props.task.is_fixed) return '固定'
  switch (props.task.status) {
    case 'in_progress':
      return '进行中'
    case 'completed':
      return '已完成'
    case 'cancelled':
      return '已取消'
    default:
      return '待办'
  }
})

const statusClass = computed(() => {
  if (props.task.is_fixed) return 'fixed'
  if (props.task.status === 'completed') return 'done'
  if (props.task.status === 'in_progress') return 'progress'
  return 'todo'
})
</script>

<template>
  <article
    class="card tappable"
    :class="statusClass"
  >
    <button
      class="check"
      :aria-label="`完成 ${task.title}`"
      @click="$emit('complete', task)"
    >
      <span aria-hidden="true">{{ task.status === 'completed' ? '✓' : '○' }}</span>
    </button>
    <button
      class="body"
      @click="$emit('open', task)"
    >
      <span
        class="title"
        :class="{ struck: task.status === 'completed' }"
      >{{ task.title }}</span>
      <span class="meta">
        <span
          class="badge"
          :class="statusClass"
        >{{ statusLabel }}</span>
        <span
          v-if="task.priority > 0"
          class="prio"
        >P{{ task.priority }}</span>
      </span>
    </button>
  </article>
</template>

<style scoped>
.card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--status-normal);
  border-radius: var(--radius-md);
}
.card.progress {
  border-left-color: var(--status-due-soon);
}
.card.done {
  border-left-color: var(--status-done);
}
.card.fixed {
  border-left-color: var(--status-muted);
}
.check {
  min-width: var(--tap-target);
  min-height: var(--tap-target);
  border: none;
  background: transparent;
  font-size: 1.2rem;
  color: var(--status-done);
  cursor: pointer;
}
.body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
  border: none;
  background: transparent;
  color: var(--color-text);
  cursor: pointer;
  min-width: 0;
}
.title.struck {
  text-decoration: line-through;
  color: var(--color-text-muted);
}
.meta {
  display: flex;
  gap: var(--space-2);
  font-size: 0.75rem;
}
.badge {
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--color-surface-2);
  color: var(--color-text-muted);
}
</style>
