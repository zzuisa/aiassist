<script setup lang="ts">
import { computed } from 'vue'
import type { AgentPlan } from '@/api/agentPlans'

const props = defineProps<{ plan: AgentPlan | null }>()

const activeStep = computed(() => props.plan?.steps.find((step) =>
  ['queued', 'running', 'waiting_confirmation'].includes(step.status),
))
const label = computed(() => {
  if (!props.plan) return ''
  const phase = {
    planning: '正在规划任务',
    executing: '正在执行 MCP 编排',
    waiting_confirmation: '等待你确认标签写入',
    verifying: '正在回读验证标签',
    reporting: '正在整理 Markdown 报告',
    complete: '任务编排已完成',
  }[props.plan.phase]
  return activeStep.value ? `${phase} · ${activeStep.value.title}` : phase
})
</script>

<template>
  <div
    v-if="plan"
    class="progress-strip"
    :class="{ active: !['success', 'partial_success', 'failed', 'cancelled'].includes(plan.status) }"
    role="status"
    aria-live="polite"
  >
    <span
      class="dot"
      aria-hidden="true"
    />
    <span class="viewport"><span class="progress-text">{{ label }}</span></span>
    <span class="count">{{ plan.counts.completed }}/{{ plan.counts.total }}</span>
  </div>
</template>

<style scoped>
.progress-strip {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
}
.dot {
  width: .55rem;
  height: .55rem;
  border-radius: 50%;
  background: var(--status-done);
}
.active .dot {
  background: var(--color-primary);
  animation: pulse 1.4s ease-in-out infinite;
}
.viewport {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
}
.progress-text {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}
.count {
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}
@keyframes pulse {
  50% { opacity: .35; transform: scale(.8); }
}
@media (prefers-reduced-motion: reduce) {
  .active .dot { animation: none; }
}
</style>
