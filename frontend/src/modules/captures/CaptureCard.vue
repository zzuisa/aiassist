<script setup lang="ts">
import { computed } from 'vue'
import type { Capture } from '@/api/captures'

const props = defineProps<{ capture: Capture }>()
defineEmits<{ (e: 'open', capture: Capture): void }>()

// Processing status is shown as an inline card state, never as repeated toasts.
const statusLabel = computed(() => {
  switch (props.capture.processing_status) {
    case 'pending':
    case 'processing':
      return '处理中'
    case 'needs_input':
      return '待补充'
    case 'failed':
      return '分析失败'
    default:
      return '已就绪'
  }
})

const title = computed(
  () => props.capture.fields.title?.value ?? '未命名收藏',
)
</script>

<template>
  <button
    class="capture-card"
    @click="$emit('open', capture)"
  >
    <div
      class="thumb"
      :data-status="capture.processing_status"
    >
      <span aria-hidden="true">🖼️</span>
    </div>
    <div class="meta">
      <span class="title">{{ title }}</span>
      <span
        class="status"
        :data-status="capture.processing_status"
      >{{ statusLabel }}</span>
      <span
        v-if="capture.possible_duplicate_of"
        class="dup"
      >可能重复</span>
    </div>
  </button>
</template>

<style scoped>
.capture-card {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  cursor: pointer;
  text-align: left;
  width: 100%;
  color: var(--color-text);
}
.thumb {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  display: grid;
  place-items: center;
}
.meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.status {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}
.status[data-status='failed'] {
  color: var(--status-urgent);
}
.status[data-status='processing'],
.status[data-status='pending'] {
  color: var(--status-due-soon);
}
.dup {
  font-size: 0.7rem;
  color: var(--status-due-soon);
}
</style>
