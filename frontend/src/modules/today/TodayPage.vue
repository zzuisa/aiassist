<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { tasksApi, type Task, type TodayDashboard } from '@/api/tasks'
import { voiceApi, type VoiceCandidate, type VoiceRecord } from '@/api/voice'
import { useTasksStore } from '@/stores/tasks'
import QuickTaskInput from '@/modules/tasks/QuickTaskInput.vue'
import QuickPlanReview from '@/modules/today/QuickPlanReview.vue'
import TaskCard from '@/modules/tasks/TaskCard.vue'
import VoiceRecorder from '@/modules/voice/VoiceRecorder.vue'
import VoiceConfirmDrawer from '@/modules/voice/VoiceConfirmDrawer.vue'

const store = useTasksStore()
const dashboard = ref<TodayDashboard | null>(null)
const loading = ref(true)
const pendingVoice = ref<VoiceRecord | null>(null)
const confirmCandidate = ref<{ id: string; candidate: VoiceCandidate } | null>(null)
const voiceError = ref('')

async function refresh(): Promise<void> {
  dashboard.value = await tasksApi.today()
}

// The daily list strictly follows the calendar: today's scheduled events,
// time-ordered. Undated open tasks live in a separate "待安排" section and can
// be swiped onto the calendar. Mutations sync both views via the store signal.
const todayList = computed(() => dashboard.value?.timeline ?? [])
const unscheduled = computed(() =>
  (dashboard.value?.todos ?? []).filter((t) => !t.start_at && t.status !== 'completed'),
)

// Resolve a terminal voice status; returns true when nothing more to poll.
async function settleVoice(rec: VoiceRecord): Promise<boolean> {
  if (rec.status === 'confirmed') {
    // Auto-confirm: the entity was already created server-side. Just refresh so
    // the new task shows up immediately — no confirmation step needed.
    pendingVoice.value = null
    await refresh()
    return true
  }
  if (rec.status === 'waiting_user' && rec.candidate) {
    // Legacy review flow: surface the confirmation drawer.
    confirmCandidate.value = { id: rec.id, candidate: rec.candidate }
    pendingVoice.value = null
    return true
  }
  if (rec.status === 'failed') {
    voiceError.value = rec.error?.message ?? '识别失败，请重试'
    pendingVoice.value = null
    return true
  }
  return false
}

async function onVoiceCreated(record: VoiceRecord): Promise<void> {
  voiceError.value = ''
  pendingVoice.value = record
  // The real-time path parses synchronously and returns a terminal status
  // (confirmed/failed) right away; the audio path stays 'parsing' and needs polling.
  if (await settleVoice(record)) return
  const poll = async (): Promise<void> => {
    const latest = await voiceApi.get(record.id)
    pendingVoice.value = latest
    if (await settleVoice(latest)) return
    if (['transcribing', 'parsing', 'uploaded'].includes(latest.status)) {
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

// Keep the Today list in sync with mutations from anywhere (including a calendar
// drag): any task change bumps the store signal and we refetch. Also refresh when
// the tab regains focus so it never shows a stale board.
watch(() => store.changedAt, () => void refresh())
function onVisible(): void {
  if (document.visibilityState === 'visible') void refresh()
}
onMounted(() => document.addEventListener('visibilitychange', onVisible))
onBeforeUnmount(() => document.removeEventListener('visibilitychange', onVisible))

onMounted(async () => {
  try {
    await refresh()
  } finally {
    loading.value = false
  }
})

// Quick-add routes through the analysis panel: the LLM splits it into scheduled
// tasks and may ask a couple of questions; the user can answer, save the plan, or
// bail out to a plain todo at any time.
const planText = ref<string | null>(null)
async function onCreate(title: string): Promise<void> {
  planText.value = title
}
async function onPlanSaved(): Promise<void> {
  planText.value = null
  await refresh()
  store.markChanged()
}
async function onPlanSaveRaw(title: string): Promise<void> {
  planText.value = null
  await store.create({ title })
  await refresh()
}

async function onComplete(task: Task): Promise<void> {
  await store.complete(task)
  await refresh()
}

// Left-swipe action: give an undated todo a concrete calendar slot (next full
// hour today, or tomorrow 09:00 if it's already late), then it shows on the
// calendar via the shared sync signal.
async function onAddToCalendar(task: Task): Promise<void> {
  const start = new Date()
  start.setMinutes(0, 0, 0)
  start.setHours(start.getHours() + 1)
  if (start.getHours() >= 22 || start.getHours() < 7) {
    start.setDate(start.getDate() + (start.getHours() >= 22 ? 1 : 0))
    start.setHours(9, 0, 0, 0)
  }
  const end = new Date(start.getTime() + 30 * 60 * 1000)
  await store.patch(task.id, {
    version: task.version,
    start_at: start.toISOString(),
    due_at: end.toISOString(),
  })
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
      <span
        v-if="voiceError"
        class="voice-error"
        role="alert"
      >{{ voiceError }}</span>
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
          @add-to-calendar="onAddToCalendar"
        />
      </section>

      <section aria-label="今日日历">
        <h2>今日日历 ({{ todayList.length }})</h2>
        <p
          v-if="todayList.length === 0"
          class="muted"
        >
          今天日历上还没有安排。
        </p>
        <transition-group
          name="list"
          tag="div"
          class="list"
        >
          <TaskCard
            v-for="t in todayList"
            :key="t.id"
            :task="t"
            @complete="onComplete"
            @open="() => {}"
            @add-to-calendar="onAddToCalendar"
          />
        </transition-group>
      </section>

      <section
        v-if="unscheduled.length"
        aria-label="待安排"
      >
        <h2>待安排 ({{ unscheduled.length }})</h2>
        <p class="muted small">左滑任务可加入日历</p>
        <transition-group
          name="list"
          tag="div"
          class="list"
        >
          <TaskCard
            v-for="t in unscheduled"
            :key="t.id"
            :task="t"
            @complete="onComplete"
            @open="() => {}"
            @add-to-calendar="onAddToCalendar"
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
          @add-to-calendar="onAddToCalendar"
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

    <QuickPlanReview
      v-if="planText"
      :text="planText"
      @saved="onPlanSaved"
      @save-raw="onPlanSaveRaw"
      @close="planText = null"
    />
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
.voice-error {
  color: var(--status-urgent);
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
