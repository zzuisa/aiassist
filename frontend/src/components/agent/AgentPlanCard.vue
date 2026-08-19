<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  PLAN_TERMINAL_STATUSES,
  type AgentPlan,
} from '@/api/agentPlans'
import AgentPlanStep from './AgentPlanStep.vue'

const props = defineProps<{ plan: AgentPlan; retrying?: boolean }>()
const emit = defineEmits<{ retry: [planId: string] }>()

const isTerminal = computed(() => PLAN_TERMINAL_STATUSES.includes(props.plan.status))
const expanded = ref(!isTerminal.value)
const userControlled = ref(false)
let previousTerminal = isTerminal.value

watch(
  () => props.plan.status,
  () => {
    const terminal = isTerminal.value
    if (!previousTerminal && terminal && !userControlled.value) expanded.value = false
    if (!terminal && !userControlled.value) expanded.value = true
    previousTerminal = terminal
  },
)

const statusLabel = computed(() => ({
  planning: '正在规划',
  pending: '等待调度',
  running: '执行中',
  waiting_user: '等待你的确认',
  success: '已完成',
  partial_success: '部分完成',
  failed: '失败',
  stalled: '已停滞',
  cancelled: '已取消',
}[props.plan.status]))

const elapsed = computed(() => {
  if (props.plan.elapsed_ms === null) return null
  return props.plan.elapsed_ms < 1000
    ? `${props.plan.elapsed_ms} ms`
    : `${(props.plan.elapsed_ms / 1000).toFixed(1)} s`
})

const retryable = computed(() =>
  ['failed', 'partial_success', 'stalled'].includes(props.plan.status)
  && (props.plan.error?.retryable || props.plan.steps.some((step) => step.error?.retryable)),
)

function toggle(): void {
  userControlled.value = true
  expanded.value = !expanded.value
}
</script>

<template>
  <section
    class="plan-card"
    :class="{ active: !isTerminal }"
    :aria-label="`执行计划：${plan.objective}`"
  >
    <button
      type="button"
      class="plan-summary"
      :aria-expanded="expanded"
      @click="toggle"
    >
      <span
        class="chevron"
        aria-hidden="true"
      >{{ expanded ? '▾' : '▸' }}</span>
      <span class="summary-main">
        <strong>{{ plan.objective }}</strong>
        <small>
          {{ statusLabel }} · {{ plan.counts.completed }}/{{ plan.counts.total }} 完成
          <template v-if="plan.counts.failed"> · {{ plan.counts.failed }} 失败</template>
          <template v-if="plan.counts.skipped"> · {{ plan.counts.skipped }} 跳过</template>
          <template v-if="elapsed"> · {{ elapsed }}</template>
        </small>
      </span>
    </button>

    <div
      v-if="expanded"
      class="plan-details"
      aria-live="polite"
    >
      <ol>
        <AgentPlanStep
          v-for="step in plan.steps"
          :key="step.step_id"
          :step="step"
        />
      </ol>
      <p
        v-if="plan.result_summary"
        class="result-summary"
      >
        {{ plan.result_summary }}
      </p>
      <p
        v-if="plan.error"
        class="error"
      >
        {{ plan.error.message }}
      </p>
      <button
        v-if="retryable"
        type="button"
        class="retry"
        :disabled="retrying"
        @click.stop="emit('retry', plan.plan_id)"
      >
        {{ retrying ? '正在重试…' : '重试失败步骤' }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.plan-card { margin: var(--space-2) 0 var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); overflow: hidden; }
.plan-card.active { border-inline-start: 3px solid var(--color-primary); }
.plan-summary { width: 100%; display: grid; grid-template-columns: 1.25rem 1fr; gap: var(--space-2); padding: var(--space-3); border: 0; text-align: start; background: transparent; color: inherit; }
.summary-main { display: grid; gap: .2rem; }
.summary-main small { color: var(--color-text-muted); }
.chevron { padding-top: .1rem; }
.plan-details { padding: 0 var(--space-3) var(--space-3); }
ol { list-style: none; padding: 0; margin: 0; }
.result-summary { margin: var(--space-2) 0 0; padding-top: var(--space-2); border-top: 1px solid var(--color-border); }
.error { color: var(--status-overdue); }
.retry { margin-top: var(--space-2); }
</style>
