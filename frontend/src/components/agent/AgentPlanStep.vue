<script setup lang="ts">
import { computed } from 'vue'
import type { AgentPlanStep } from '@/api/agentPlans'

const props = defineProps<{ step: AgentPlanStep }>()

const statusLabel = computed(() => ({
  pending: '等待依赖',
  queued: '已排队',
  running: '执行中',
  waiting_confirmation: '等待确认',
  success: '已完成',
  partial_success: '部分完成',
  failed: '失败',
  blocked: '已阻塞',
  skipped: '已跳过',
  stalled: '已停滞',
  cancelled: '已取消',
}[props.step.status]))

const duration = computed(() => {
  if (props.step.duration_ms === null) return null
  return props.step.duration_ms < 1000
    ? `${props.step.duration_ms} ms`
    : `${(props.step.duration_ms / 1000).toFixed(1)} s`
})
</script>

<template>
  <li
    class="plan-step"
    :class="`status-${step.status}`"
  >
    <span
      class="status-icon"
      aria-hidden="true"
    >{{ step.status === 'running' ? '●' : step.status === 'success' ? '✓' : step.status === 'failed' ? '!' : '○' }}</span>
    <div class="step-main">
      <div class="step-heading">
        <strong>{{ step.position }}. {{ step.title }}</strong>
        <span class="status-label">{{ statusLabel }}</span>
      </div>
      <p>{{ step.agent.name }} · {{ step.tool_name }}</p>
      <p v-if="step.stage_label">
        {{ step.stage_label }}
      </p>
      <progress
        v-if="step.progress"
        :value="step.progress.current"
        :max="Math.max(step.progress.total, 1)"
      >
        {{ step.progress.current }}/{{ step.progress.total }}
      </progress>
      <small v-if="step.result_summary">{{ step.result_summary }}</small>
      <small
        v-if="step.error"
        class="error"
      >{{ step.error.message }}</small>
      <small v-if="duration">用时 {{ duration }} · 尝试 {{ step.attempt_count }} 次</small>
      <small v-if="step.depends_on.length">依赖：{{ step.depends_on.join('、') }}</small>
    </div>
  </li>
</template>

<style scoped>
.plan-step { display: grid; grid-template-columns: 1.25rem 1fr; gap: var(--space-2); padding: var(--space-2) 0; }
.plan-step + .plan-step { border-top: 1px solid var(--color-border); }
.status-icon { font-weight: 700; text-align: center; }
.status-running .status-icon { color: var(--color-primary); animation: pulse 1.2s ease-in-out infinite; }
.status-success .status-icon { color: var(--status-success); }
.status-failed .status-icon, .error { color: var(--status-overdue); }
.step-main { min-width: 0; display: grid; gap: .2rem; }
.step-heading { display: flex; justify-content: space-between; gap: var(--space-2); }
.status-label { color: var(--color-text-muted); white-space: nowrap; }
p, small { margin: 0; overflow-wrap: anywhere; }
p, small { color: var(--color-text-muted); }
progress { width: 100%; }
@keyframes pulse { 50% { opacity: .35; } }
@media (prefers-reduced-motion: reduce) { .status-running .status-icon { animation: none; } }
</style>
