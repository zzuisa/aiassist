<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { tasksApi, type Task, type TodayDashboard } from '@/api/tasks'
import { voiceApi, type VoiceCandidate, type VoiceRecord } from '@/api/voice'
import { useTasksStore } from '@/stores/tasks'
import QuickTaskInput from '@/modules/tasks/QuickTaskInput.vue'
import TaskCard from '@/modules/tasks/TaskCard.vue'
import VoiceRecorder from '@/modules/voice/VoiceRecorder.vue'
import VoiceConfirmDrawer from '@/modules/voice/VoiceConfirmDrawer.vue'

const store = useTasksStore()
const dashboard = ref<TodayDashboard | null>(null)
const loading = ref(true)
const pendingVoice = ref<VoiceRecord | null>(null)
const confirmCandidate = ref<{ id: string; candidate: VoiceCandidate } | null>(null)

async function refresh(): Promise<void> {
  dashboard.value = await tasksApi.today()
}

async function onVoiceCreated(record: VoiceRecord): Promise<void> {
  pendingVoice.value = record
  // Poll the record until it is ready for confirmation (SSE also drives this in
  // the full app; polling keeps the Today page self-contained).
  const poll = async (): Promise<void> => {
    const latest = await voiceApi.get(record.id)
    pendingVoice.value = latest
    if (latest.status === 'waiting_user' && latest.candidate) {
      confirmCandidate.value = { id: latest.id, candidate: latest.candidate }
    } else if (['transcribing', 'parsing', 'uploaded'].includes(latest.status)) {
      setTimeout(poll, 1500)
    }
  }
  setTimeout(poll, 1500)
}

async function onVoiceConfirmed(): Promise<void> {
  confirmCandidate.value = null
  pendingVoice.value = null
  await refresh()
}

onMounted(async () => {
  try {
    await refresh()
  } finally {
    loading.value = false
  }
})

async function onCreate(title: string): Promise<void> {
  await store.create({ title })
  await refresh()
}

async function onComplete(task: Task): Promise<void> {
  await tasksApi.complete(task.id, task.version)
  await refresh()
}
</script>

<template>
  <main class="today">
    <header class="head">
      <h1>今日</h1>
      <span
        v-if="dashboard"
        class="date"
      >{{ dashboard.date }}</span>
    </header>

    <QuickTaskInput @create="onCreate" />

    <div class="voice-row">
      <VoiceRecorder @created="onVoiceCreated" />
      <span
        v-if="pendingVoice && pendingVoice.status !== 'waiting_user'"
        class="voice-status"
        role="status"
      >语音处理中…</span>
    </div>

    <p
      v-if="loading"
      class="muted"
    >
      加载中…
    </p>

    <template v-else-if="dashboard">
      <section
        v-if="dashboard.current_task"
        class="current"
        aria-label="当前任务"
      >
        <h2>现在最该做</h2>
        <TaskCard
          :task="dashboard.current_task"
          @complete="onComplete"
          @open="() => {}"
        />
      </section>

      <section aria-label="待办">
        <h2>待办 ({{ dashboard.todos.length }})</h2>
        <p
          v-if="dashboard.todos.length === 0"
          class="muted"
        >
          今天还没有待办。
        </p>
        <transition-group
          name="list"
          tag="div"
          class="list"
        >
          <TaskCard
            v-for="t in dashboard.todos"
            :key="t.id"
            :task="t"
            @complete="onComplete"
            @open="() => {}"
          />
        </transition-group>
      </section>

      <section
        v-if="dashboard.overdue.length"
        aria-label="逾期"
      >
        <h2 class="overdue">
          逾期 ({{ dashboard.overdue.length }})
        </h2>
        <transition-group
          name="list"
          tag="div"
          class="list"
        >
          <TaskCard
            v-for="t in dashboard.overdue"
            :key="t.id"
            :task="t"
            @complete="onComplete"
            @open="() => {}"
          />
        </transition-group>
      </section>
    </template>

    <div
      v-if="confirmCandidate"
      class="overlay"
    >
      <VoiceConfirmDrawer
        :record-id="confirmCandidate.id"
        :candidate="confirmCandidate.candidate"
        @confirmed="onVoiceConfirmed"
        @discard="confirmCandidate = null"
      />
    </div>
  </main>
</template>

<style scoped>
.today {
  padding: var(--space-4);
  padding-top: calc(var(--safe-top) + var(--space-4));
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  max-width: 720px;
  margin: 0 auto;
}
.voice-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.voice-status {
  color: var(--status-ai);
  font-size: 0.85rem;
}
.overlay {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.35);
  padding: var(--space-4);
  z-index: 20;
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.date {
  color: var(--color-text-muted);
}
.list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  position: relative; /* anchor for list-leave absolute positioning */
}
.muted {
  color: var(--color-text-muted);
}
.overdue {
  color: var(--status-urgent);
}
h2 {
  font-size: 1rem;
  margin: 0 0 var(--space-2);
}
</style>
