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

const conversation = useAgentConversationsStore()

// Existing single-task result/confirmation surfacing (execution records,
// pending writes, capability-gap notices). Nothing populates these from a
// conversation Turn yet — wiring task results INTO the chat timeline is
// Phase 6/US4; these components are kept mounted and working so that phase
// only needs to start feeding them data.
const task = ref<AgentTaskDetail | null>(null)
const taskError = ref('')
const confirmations = ref<PendingWrite[]>([])
const records = ref<ExecutionRecord[]>([])
const decidingId = ref<string | null>(null)
let linkedTaskId: string | null = null

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
  () => conversation.messages,
  (messages) => {
    const latest = [...messages]
      .reverse()
      .map((message) => message.content.task_id)
      .find((value): value is string => typeof value === 'string')
    if (latest && latest !== linkedTaskId) {
      linkedTaskId = latest
      void refreshLinkedTask(latest)
    }
  },
  { deep: true },
)

onMounted(conversation.startFreshConversation)
onBeforeUnmount(() => conversation.reset())
</script>

<template>
  <main class="agent-page">
    <header>
      <h1>自助 Agent</h1>
      <p>用自然语言和我聊聊，或者直接说说你想让我处理什么。</p>
    </header>

    <ConversationPanel
      :messages="conversation.messages"
      :loading="conversation.loadingHistory"
      :sending="conversation.sending"
      :error="conversation.error"
      @send="(text) => conversation.sendMessage(text)"
    />

    <AgentTurnRetry
      :turns="conversation.activeTurns.filter((item) => item.status === 'stalled' || item.status === 'failed')"
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

    <CapabilityGapNotice
      v-if="capabilityGap"
      :gap="capabilityGap"
    />

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
      v-else-if="textualResult"
      class="text-result"
    >{{ textualResult }}</pre>
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
}
.confirmations {
  display: grid;
  gap: var(--space-3);
}
.text-result {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.error {
  color: var(--status-overdue);
}
</style>
