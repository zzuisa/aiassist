<script setup lang="ts">
import { computed } from 'vue'
import type { Turn } from '@/api/agentConversations'
import {
  PLAN_TERMINAL_STATUSES,
  type AgentPlan,
  type AgentPlanStep,
} from '@/api/agentPlans'

const props = withDefaults(defineProps<{
  plan: AgentPlan | null
  turn?: Turn | null
  sending?: boolean
}>(), {
  turn: null,
  sending: false,
})

const planMatchesLatestTurn = computed(() =>
  !props.turn || props.plan?.turn_id === props.turn.id,
)
const activePlan = computed(() =>
  props.sending || !planMatchesLatestTurn.value ? null : props.plan,
)
const activeStep = computed(() => activePlan.value?.steps.find((step) =>
  ['queued', 'running', 'waiting_confirmation'].includes(step.status),
))
const isPlanTerminal = computed(() =>
  !!activePlan.value && PLAN_TERMINAL_STATUSES.includes(activePlan.value.status),
)
const visible = computed(() => props.sending || !!props.turn || !!props.plan)

const phaseLabel = computed(() => {
  if (props.sending) return '正在接收任务'
  if (!activePlan.value && props.turn) {
    return {
      accepted: '任务已收到',
      routing: '正在思考',
      waiting_clarification: '等待你补充信息',
      executing: '已识别为复杂任务，正在编排',
      waiting_confirmation: '等待你确认',
      success: '任务已完成',
      partial_success: '任务部分完成',
      failed: '任务处理失败',
      stalled: '任务暂时停滞',
      cancelled: '任务已取消',
    }[props.turn.status]
  }
  if (!activePlan.value) return '正在准备'
  return {
    planning: '正在规划任务',
    executing: '正在执行 MCP 编排',
    waiting_confirmation: '等待你确认标签写入',
    verifying: '正在回读验证结果',
    reporting: '正在整理 Markdown 报告',
    complete: '任务编排已完成',
  }[activePlan.value.phase]
})

const detailLabel = computed(() => {
  if (props.sending) return '消息已显示，正在建立任务上下文'
  if (!activePlan.value) return props.turn?.current_step || '等待服务开始处理'
  const step = activeStep.value
  if (!step) return activePlan.value.result_summary || '正在同步最新状态'
  return step.stage_label ? `${step.title} · ${step.stage_label}` : step.title
})

function stepMarker(step: AgentPlanStep): string {
  if (['success', 'partial_success'].includes(step.status)) return '✓'
  if (step.status === 'running') return '进行中'
  if (step.status === 'waiting_confirmation') return '待确认'
  if (['failed', 'blocked', 'stalled'].includes(step.status)) return '受阻'
  if (['skipped', 'cancelled'].includes(step.status)) return '跳过'
  return '接下来'
}

const roadmap = computed(() => activePlan.value?.steps
  .map((step) => `${stepMarker(step)} ${step.position}. ${step.title}`)
  .join('　→　') ?? '')
const showRoadmap = computed(() =>
  !!activePlan.value && activePlan.value.steps.length > 1 && !isPlanTerminal.value,
)
const progressCurrent = computed(() =>
  activeStep.value?.progress?.current ?? activePlan.value?.counts.completed ?? 0,
)
const progressTotal = computed(() =>
  activeStep.value?.progress?.total ?? activePlan.value?.counts.total ?? 0,
)
const progressLabel = computed(() => {
  const step = activeStep.value
  if (step?.progress) {
    return `本步骤 ${step.progress.current}/${step.progress.total}`
  }
  if (activePlan.value) {
    return `总进度 ${activePlan.value.counts.completed}/${activePlan.value.counts.total}`
  }
  return ''
})
</script>

<template>
  <section
    v-if="visible"
    class="progress-strip"
    :class="{ active: sending || (activePlan && !isPlanTerminal) }"
    role="status"
    aria-live="polite"
    aria-atomic="true"
  >
    <div class="status-row">
      <span
        class="dot"
        aria-hidden="true"
      />
      <span class="status-copy">
        <strong>{{ phaseLabel }}</strong>
        <small>{{ detailLabel }}</small>
      </span>
      <span
        v-if="activePlan"
        class="count"
      >{{ activePlan.counts.completed }}/{{ activePlan.counts.total }}</span>
    </div>

    <div
      v-if="showRoadmap"
      class="marquee"
      aria-hidden="true"
    >
      <span class="marquee-content">{{ roadmap }}</span>
    </div>
    <span
      v-if="showRoadmap"
      class="sr-only"
    >任务计划：{{ roadmap }}</span>

    <div
      v-if="activePlan"
      class="micro-progress"
    >
      <progress
        :value="progressCurrent"
        :max="Math.max(progressTotal, 1)"
        :aria-label="progressLabel"
      />
      <small>{{ progressLabel }}</small>
    </div>
  </section>
</template>

<style scoped>
.progress-strip {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-inline-start: 3px solid var(--status-done);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  overflow: hidden;
}
.progress-strip.active { border-inline-start-color: var(--color-primary); }
.status-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-2);
}
.status-copy { min-width: 0; display: grid; gap: .1rem; }
.status-copy strong,
.status-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.status-copy small,
.count,
.micro-progress small { color: var(--color-text-muted); }
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
.count { font-variant-numeric: tabular-nums; }
.marquee {
  min-width: 0;
  overflow: hidden;
  padding-block: .2rem;
  border-block: 1px solid var(--color-border);
  white-space: nowrap;
  mask-image: linear-gradient(90deg, transparent, var(--color-mask-opaque) 5%, var(--color-mask-opaque) 95%, transparent);
}
.marquee-content {
  display: inline-block;
  padding-inline-start: 100%;
  color: var(--color-text-muted);
  animation: marquee 20s linear infinite;
}
.micro-progress {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-2);
}
.micro-progress progress { width: 100%; height: .35rem; accent-color: var(--color-primary); }
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
@keyframes pulse { 50% { opacity: .35; transform: scale(.8); } }
@keyframes marquee { to { transform: translateX(-100%); } }
@media (prefers-reduced-motion: reduce) {
  .active .dot,
  .marquee-content { animation: none; }
  .marquee-content { padding-inline-start: 0; }
  .marquee { text-overflow: ellipsis; }
}
</style>
