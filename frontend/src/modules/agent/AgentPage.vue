<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import {
  agentApi,
  parseAgentReply,
  type AgentArticleResult,
  type AgentTaskDetail,
} from '@/api/agent'
import AgentStatusPanel from '@/components/agent/AgentStatusPanel.vue'

const requestText = ref('')
const task = ref<AgentTaskDetail | null>(null)
const error = ref('')
const submitting = ref(false)
let pollTimer: number | null = null

const reply = computed(() => parseAgentReply(task.value?.result_summary ?? null))
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

function stopPolling(): void {
  if (pollTimer !== null) window.clearTimeout(pollTimer)
  pollTimer = null
}

async function refresh(taskId: string): Promise<void> {
  task.value = await agentApi.getTask(taskId)
  if (['pending', 'running'].includes(task.value.status)) {
    pollTimer = window.setTimeout(() => void refresh(taskId), 1000)
  }
}

async function submit(): Promise<void> {
  const value = requestText.value.trim()
  if (!value || submitting.value) return
  stopPolling()
  submitting.value = true
  error.value = ''
  try {
    const created = await agentApi.createTask(value)
    await refresh(created.task_id)
  } catch {
    error.value = '任务创建失败，请稍后重试。'
  } finally {
    submitting.value = false
  }
}

onBeforeUnmount(stopPolling)
</script>

<template>
  <main class="agent-page">
    <header>
      <h1>自助 Agent</h1>
      <p>用自然语言查询和处理你的数据。</p>
    </header>

    <form
      class="composer"
      @submit.prevent="submit"
    >
      <label for="agent-request">你希望系统做什么？</label>
      <textarea
        id="agent-request"
        v-model="requestText"
        rows="3"
        maxlength="4000"
        placeholder="例如：给我最近 10 篇文章"
      />
      <button
        type="submit"
        :disabled="submitting || !requestText.trim()"
      >
        {{ submitting ? '正在提交…' : '开始执行' }}
      </button>
    </form>

    <p
      v-if="error"
      class="error"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-if="task && ['pending', 'running'].includes(task.status)"
      role="status"
    >
      正在处理：{{ task.runs[0]?.current_task ?? task.request_text }}
    </p>

    <AgentStatusPanel :task-id="task?.task_id" />

    <section
      v-if="articles.length"
      class="results"
      aria-label="文章查询结果"
    >
      <article
        v-for="article in articles"
        :key="article.id"
        class="result-card"
      >
        <RouterLink :to="article.link">
          {{ article.title }}
        </RouterLink>
        <p
          v-if="article.category || article.tags.length"
          class="meta"
        >
          <span v-if="article.category">{{ article.category }}</span>
          <span
            v-for="tag in article.tags"
            :key="tag"
          >#{{ tag }}</span>
        </p>
      </article>
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
.composer {
  display: grid;
  gap: var(--space-2);
}
textarea {
  width: 100%;
  resize: vertical;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
}
button {
  min-height: var(--tap-target);
  justify-self: end;
}
.results {
  display: grid;
  gap: var(--space-2);
}
.result-card {
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  color: var(--color-text-muted);
}
.text-result {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.error {
  color: var(--status-overdue);
}
</style>
