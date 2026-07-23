<script setup lang="ts">
import { computed } from 'vue'
import type { DependencyState } from '@/api/settings'

// Shows only whether a provider is configured/ready — never any secret value.
const props = defineProps<{ label: string; state: DependencyState }>()

const text = computed(() => {
  switch (props.state.state) {
    case 'ready':
      return '已配置'
    case 'degraded':
      return '降级'
    default:
      return '未配置'
  }
})
</script>

<template>
  <div class="dep">
    <span class="label">{{ label }}</span>
    <span
      class="state"
      :data-state="state.state"
    >{{ text }}</span>
    <span
      v-if="state.provider_key"
      class="provider"
    >{{ state.provider_key }}</span>
  </div>
</template>

<style scoped>
.dep {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
}
.label {
  min-width: 80px;
}
.state {
  font-size: 0.75rem;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--color-surface-2);
}
.state[data-state='ready'] {
  color: var(--status-done);
}
.state[data-state='degraded'] {
  color: var(--status-due-soon);
}
.state[data-state='unconfigured'] {
  color: var(--color-text-muted);
}
.provider {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}
</style>
