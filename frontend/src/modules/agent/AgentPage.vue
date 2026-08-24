<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  agentApi,
  parseAgentReply,
  type ConfirmationDecision,
  type ExecutionRecord,
  type PendingWrite,
  type AgentTaskDetail,
} from '@/api/agent'
import { useAgentConversationsStore } from '@/stores/agentConversations'
import AgentStatusPanel from '@/components/agent/AgentStatusPanel.vue'
import AgentTurnRetry from '@/components/agent/AgentTurnRetry.vue'
import CapabilityGapNotice from '@/components/agent/CapabilityGapNotice.vue'
import ConfirmationCard from '@/components/agent/ConfirmationCard.vue'
import ConversationPanel from '@/components/agent/ConversationPanel.vue'
import ExecutionRecordList from '@/components/agent/ExecutionRecordList.vue'
import TaskReportCard from '@/components/agent/TaskReportCard.vue'
import AgentProgressStrip from '@/components/agent/AgentProgressStrip.vue'
import AgentResultList from '@/components/agent/AgentResultList.vue'
import { presentAgentResult } from '@/components/agent/resultPresentation'
import { agentPlansApi, type AgentTaskReport } from '@/api/agentPlans'
import BaseCard from '@/components/base/BaseCard.vue'

const conversation = useAgentConversationsStore()

const task = ref<AgentTaskDetail | null>(null)
const taskError = ref('')
const confirmations = ref<PendingWrite[]>([])
const records = ref<ExecutionRecord[]>([])
const decidingId = ref<string | null>(null)
const retryingPlanId = ref<string | null>(null)
const report = ref<AgentTaskReport | null>(null)
let linkedTaskId: string | null = null
let linkedPlanVersion = -1

const reply = computed(() => parseAgentReply(task.value?.result_summary ?? null))
const capabilityGap = computed(() => reply.value?.能力缺口 ?? null)
const presentedResult = computed(() => presentAgentResult(reply.value?.处理结果))
const retryableTurns = computed(() =>
  conversation.activeTurns
    .filter((item) => item.status === 'stalled' || item.status === 'failed')
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .slice(0, 1),
)
const latestUserMessageId = computed(() => [...conversation.messages]
  .reverse()
  .find((message) => message.role === 'user')?.id ?? null)
const latestPlan = computed(() => [...conversation.plans]
  .reverse()
  .find((plan) => plan.user_message_id === latestUserMessageId.value) ?? null)
const latestTurn = computed(() => [...conversation.activeTurns]
  .sort((left, right) => left.created_at.localeCompare(right.created_at))
  .at(-1) ?? null)

async function decide(confirmation: PendingWrite, decision: ConfirmationDecision): Promise<void> {
  if (!task.value || decidingId.value) return
  decidingId.value = confirmation.confirmation_id
  taskError.value = ''
  try {
    await agentApi.decideConfirmation(
      task.value.task_id,
      confirmation.confirmation_id,
      decision,
    )
    const [nextTask, nextConfirmations, nextRecords] = await Promise.all([
      agentApi.getTask(task.value.task_id),
      agentApi.listConfirmations(task.value.task_id),
      agentApi.listRecords(task.value.task_id),
    ])
    task.value = nextTask
    confirmations.value = nextConfirmations
    records.value = nextRecords
  } catch {
    taskError.value = '确认操作失败，数据可能已变化，请刷新后重试。'
  } finally {
    decidingId.value = null
  }
}

async function refreshLinkedTask(taskId: string): Promise<void> {
  try {
    const [nextTask, nextConfirmations, nextRecords] = await Promise.all([
      agentApi.getTask(taskId),
      agentApi.listConfirmations(taskId),
      agentApi.listRecords(taskId),
    ])
    task.value = nextTask
    confirmations.value = nextConfirmations
    records.value = nextRecords
  } catch {
    taskError.value = '任务详情加载失败，请稍后刷新。'
  }
}

watch(
  [() => conversation.plans, () => conversation.messages],
  ([plans, messages]) => {
    const latestPlan = plans.at(-1)
    const planTaskId = latestPlan?.task_id
    const messageTaskId = [...messages]
      .reverse()
      .map((message) => message.content.task_id)
      .find((value): value is string => typeof value === 'string')
    const latest = planTaskId ?? messageTaskId
    const planAdvanced = latestPlan !== undefined && latestPlan.version > linkedPlanVersion
    if (latest && (latest !== linkedTaskId || planAdvanced)) {
      if (latest !== linkedTaskId) report.value = null
      linkedTaskId = latest
      linkedPlanVersion = latestPlan?.version ?? linkedPlanVersion
      void refreshLinkedTask(latest)
    }
    if (
      latestPlan
      && ['success', 'partial_success'].includes(latestPlan.status)
      && report.value?.plan_id !== latestPlan.plan_id
    ) {
      void agentPlansApi.getReport(latestPlan.plan_id).then((value) => {
        report.value = value
      }).catch(() => undefined)
    }
  },
  { deep: true },
)

onMounted(() => {
  conversation.startFreshConversation()
})
onBeforeUnmount(() => conversation.reset())

async function retryPlan(planId: string): Promise<void> {
  retryingPlanId.value = planId
  try {
    await conversation.retryPlan(planId)
  } finally {
    retryingPlanId.value = null
  }
}
</script>

<template>
  <main class="agent-page">
    <header class="page-heading">
      <p class="eyebrow">
        AI WORKSPACE · AGENT ORCHESTRATION
      </p>
      <h1>把任务交给<br>Agent 协作完成。</h1>
      <p>用自然语言查询、分析和处理你的内容。所有写入操作都会先展示预览并等待确认。</p>
    </header>

    <BaseCard
      class="workspace-card"
      elevated
    >
      <div class="workspace-card__head">
        <div>
          <span>CONVERSATION</span>
          <h2>当前协作会话</h2>
        </div>
        <span class="privacy-badge">内部会话</span>
      </div>
      <ConversationPanel
        :messages="conversation.messages"
        :sending="conversation.sending"
        :error="conversation.error"
        :plans="conversation.plans"
        :retrying-plan-id="retryingPlanId"
        @send="(text) => conversation.sendMessage(text)"
        @retry-plan="retryPlan"
      >
        <template #status>
          <AgentProgressStrip
            :plan="latestPlan"
            :turn="latestTurn"
            :sending="conversation.sending"
          />
        </template>
      </ConversationPanel>
    </BaseCard>

    <AgentTurnRetry
      :turns="retryableTurns"
      @retry="conversation.retryTurn"
    />

    <p
      v-if="taskError"
      class="error"
      role="alert"
    >
      {{ taskError }}
    </p>

    <AgentStatusPanel :task-id="task?.task_id" />

    <section
      v-if="confirmations.length"
      class="confirmations"
      aria-label="写入确认"
    >
      <ConfirmationCard
        v-for="confirmation in confirmations"
        :key="confirmation.confirmation_id"
        :confirmation="confirmation"
        :deciding="decidingId === confirmation.confirmation_id"
        @decide="(decision) => decide(confirmation, decision)"
      />
    </section>

    <ExecutionRecordList :records="records" />

    <TaskReportCard
      v-if="report"
      :report="report"
    />

    <CapabilityGapNotice
      v-if="capabilityGap"
      :gap="capabilityGap"
    />

    <section
      v-if="!report && (presentedResult.items.length || presentedResult.summary)"
      class="result-panel"
      aria-labelledby="agent-result-heading"
    >
      <h2 id="agent-result-heading">
        处理结果
      </h2>
      <AgentResultList
        :items="presentedResult.items"
        :summary="presentedResult.summary"
      />
    </section>
  </main>
</template>

<style scoped>
.agent-page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 4.5rem var(--page-padding) 6rem;
  display: grid;
  gap: var(--space-6);
}
.page-heading {
  max-width: 820px;
}
.eyebrow {
  margin: 0;
  color: var(--color-accent);
  font-size: var(--text-xs);
  font-weight: 800;
  letter-spacing: var(--tracking-label);
}
.page-heading h1 {
  margin: var(--space-3) 0 var(--space-5);
  font: 700 clamp(2.8rem, 6vw, 5.5rem) / 0.95 var(--font-serif);
  letter-spacing: -0.045em;
}
.page-heading > p:last-child {
  max-width: 680px;
  margin: 0;
  color: var(--color-text-muted);
  line-height: 1.7;
}
.workspace-card {
  padding: 0;
  overflow: hidden;
}
.workspace-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--color-border);
}
.workspace-card__head span:first-child {
  color: var(--color-accent);
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.14em;
}
.workspace-card__head h2 {
  margin: 0.2rem 0 0;
  font: 700 1.5rem var(--font-serif);
}
.privacy-badge {
  flex: none;
  padding: 0.35rem 0.55rem;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-accent);
  font-size: var(--text-xs);
}
.confirmations {
  display: grid;
  gap: var(--space-3);
}
.result-panel {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
}
.result-panel h2 { margin: 0; font-size: 1rem; }
.error {
  color: var(--status-overdue);
}

@media (max-width: 700px) {
  .agent-page {
    padding-top: 3.5rem;
    padding-bottom: calc(6rem + var(--safe-bottom));
    gap: var(--space-4);
  }

  .page-heading h1 {
    font-size: 3.25rem;
  }

  .workspace-card__head {
    padding: var(--space-4);
  }
}
</style>
