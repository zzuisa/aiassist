<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  agentApi,
  parseAgentReply,
  type ConfirmationDecision,
  type AgentArticleResult,
  type ExecutionRecord,
  type PendingWrite,
  type AgentTaskDetail,
} from '@/api/agent'
import { useAgentConversationsStore } from '@/stores/agentConversations'
import AgentStatusPanel from '@/components/agent/AgentStatusPanel.vue'
import AgentTurnRetry from '@/components/agent/AgentTurnRetry.vue'
import ArticleResultCard from '@/components/agent/ArticleResultCard.vue'
import CapabilityGapNotice from '@/components/agent/CapabilityGapNotice.vue'
import ConfirmationCard from '@/components/agent/ConfirmationCard.vue'
import ConversationPanel from '@/components/agent/ConversationPanel.vue'
import ExecutionRecordList from '@/components/agent/ExecutionRecordList.vue'
import TaskReportCard from '@/components/agent/TaskReportCard.vue'
import AgentProgressStrip from '@/components/agent/AgentProgressStrip.vue'
import { agentPlansApi, type AgentTaskReport } from '@/api/agentPlans'

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
const articles = computed<AgentArticleResult[]>(() => {
  const result = reply.value?.处理结果
  return Array.isArray(result) ? (result as AgentArticleResult[]) : []
})
const textualResult = computed(() => {
  const result = reply.value?.处理结果
  if (typeof result === 'string') return result
  if (result && !Array.isArray(result)) return JSON.stringify(result, null, 2)
  return ''
})
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
    <header>
      <h1>自助 Agent</h1>
      <p>用自然语言和我聊聊，或者直接说说你想让我处理什么。</p>
    </header>

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

    <details
      v-if="articles.length || textualResult"
      class="result-panel"
    >
      <summary>
        处理结果
        <span v-if="articles.length">（{{ articles.length }} 项）</span>
      </summary>
      <section
        v-if="articles.length"
        class="results"
        aria-label="文章查询结果"
      >
        <ArticleResultCard
          v-for="article in articles"
          :key="article.id"
          :article="article"
        />
      </section>
      <pre
        v-else
        class="text-result"
      >{{ textualResult }}</pre>
    </details>
  </main>
</template>

<style scoped>
.agent-page {
  max-width: 760px;
  margin: 0 auto;
  padding: var(--space-4);
  display: grid;
  gap: var(--space-4);
}
.results {
  display: grid;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.confirmations {
  display: grid;
  gap: var(--space-3);
}
.text-result {
  max-height: 16rem;
  margin: var(--space-2) 0 0;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.result-panel {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
}
.result-panel summary {
  cursor: pointer;
  font-weight: 600;
}
.error {
  color: var(--status-overdue);
}
</style>
