<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import FullCalendar from '@fullcalendar/vue3'
import timeGridPlugin from '@fullcalendar/timegrid'
import listPlugin from '@fullcalendar/list'
import interactionPlugin from '@fullcalendar/interaction'
import type { CalendarOptions, EventDropArg } from '@fullcalendar/core'
import type { EventResizeDoneArg } from '@fullcalendar/interaction'
import { calendarApi, type SchedulePreview, type Task, type WeekCalendar } from '@/api/calendar'
import { persistReschedule } from '@/modules/calendar/useReschedule'
import { computeSlotRange } from '@/modules/calendar/slotRange'
import { useTasksStore } from '@/stores/tasks'
import SchedulePreviewDrawer from '@/modules/calendar/SchedulePreviewDrawer.vue'

const tasks = useTasksStore()
const week = ref<WeekCalendar | null>(null)
const preview = ref<SchedulePreview | null>(null)
const banner = ref('')
const dragging = ref(false)

function mondayOf(d: Date): string {
  const day = d.getDay() || 7
  const monday = new Date(d)
  monday.setDate(d.getDate() - day + 1)
  return monday.toISOString().slice(0, 10)
}

const startsOn = ref(mondayOf(new Date()))

async function load(): Promise<void> {
  week.value = await calendarApi.week(startsOn.value)
}

onMounted(load)

const calendarEvents = computed(() =>
  (week.value?.events ?? []).map((t) => ({
    id: t.id,
    title: t.title,
    start: t.start_at ?? undefined,
    end: t.due_at ?? undefined,
    editable: !t.is_fixed, // fixed events are not draggable/resizable
    color: t.is_fixed ? 'var(--status-muted)' : 'var(--status-normal)',
    extendedProps: { task: t },
  })),
)

// --- Optimistic drag with a debounced batch flush ---------------------------
// Rapid drags update the screen instantly and are queued locally; we sync to the
// backend only after the user pauses (or leaves the page). This keeps heavy,
// repeated reschedules snappy instead of a round-trip per drag.
interface PendingMove {
  task: Task
  startAt: string | null
  dueAt: string | null
  revert: () => void
}
const pending = new Map<string, PendingMove>()
const pendingCount = ref(0)
let flushTimer: ReturnType<typeof setTimeout> | null = null
const FLUSH_IDLE_MS = 1500

function onChange(arg: EventDropArg | EventResizeDoneArg): void {
  const task = arg.event.extendedProps.task as Task
  // Keep only the latest position per task; the newest drag wins.
  pending.set(task.id, {
    task,
    startAt: arg.event.start?.toISOString() ?? null,
    dueAt: arg.event.end?.toISOString() ?? null,
    revert: arg.revert,
  })
  pendingCount.value = pending.size
  scheduleFlush()
}

function scheduleFlush(): void {
  if (flushTimer) clearTimeout(flushTimer)
  flushTimer = setTimeout(() => void flush(), FLUSH_IDLE_MS)
}

async function flush(): Promise<void> {
  if (flushTimer) {
    clearTimeout(flushTimer)
    flushTimer = null
  }
  if (pending.size === 0) return
  const batch = [...pending.values()]
  pending.clear()
  pendingCount.value = 0

  const results = await Promise.all(
    batch.map((m) => persistReschedule(m.task, m.startAt, m.dueAt)),
  )
  let failed = false
  results.forEach((outcome, i) => {
    if (!outcome.ok) {
      failed = true
      batch[i].revert() // put this event back where it was
      banner.value =
        outcome.reason === 'version_conflict'
          ? '部分改动与其他修改冲突，已恢复并刷新。'
          : outcome.reason === 'fixed_event'
            ? '固定事件不能被移动，已恢复。'
            : '部分改动保存失败，已恢复。'
    }
  })
  if (!failed) banner.value = ''
  // Resync truth (versions/conflicts) and let the Today list reflect the moves.
  await load()
  tasks.markChanged()
}

// Never lose queued moves: flush when the tab is backgrounded or on unmount.
function onHidden(): void {
  if (document.visibilityState === 'hidden') void flush()
}
onMounted(() => document.addEventListener('visibilitychange', onHidden))
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onHidden)
  void flush()
})

async function requestPreview(): Promise<void> {
  if (!week.value) return
  const scopeStart = new Date(startsOn.value).toISOString()
  const scopeEnd = new Date(new Date(startsOn.value).getTime() + 7 * 864e5).toISOString()
  const { preview_id } = await calendarApi.createPreview(scopeStart, scopeEnd)
  preview.value = await calendarApi.getPreview(preview_id)
}

async function onApplied(): Promise<void> {
  preview.value = null
  await load()
  tasks.markChanged()
}

const slotRange = computed(() => computeSlotRange(week.value?.events ?? []))

const options = computed<CalendarOptions>(() => ({
  plugins: [timeGridPlugin, listPlugin, interactionPlugin],
  initialView: 'timeGridWeek',
  initialDate: startsOn.value,
  editable: true,
  droppable: true,
  height: 'auto',
  expandRows: true,
  nowIndicator: true,
  allDaySlot: false,
  // Touch: a short long-press starts a drag without hijacking scroll.
  longPressDelay: 250,
  eventLongPressDelay: 250,
  selectLongPressDelay: 250,
  // Collapse empty early/late hours to the range that actually has events.
  slotMinTime: slotRange.value.min,
  slotMaxTime: slotRange.value.max,
  scrollTime: slotRange.value.min,
  // Overlapping events stack up to 2 side-by-side; the rest fold into a
  // "+N 更多" popover so nothing is hidden behind another event.
  slotEventOverlap: false,
  eventMaxStack: 2,
  moreLinkClick: 'popover',
  moreLinkContent: (arg) => `+${arg.num} 更多`,
  headerToolbar: { left: 'prev,next', center: 'title', right: 'timeGridWeek,listWeek' },
  events: calendarEvents.value,
  eventDrop: onChange,
  eventResize: onChange,
  eventDragStart: () => (dragging.value = true),
  eventDragStop: () => (dragging.value = false),
  eventResizeStart: () => (dragging.value = true),
  eventResizeStop: () => (dragging.value = false),
}))
</script>

<template>
  <div
    class="calendar-layout"
    :class="{ dragging }"
  >
    <main class="calendar">
      <header class="bar">
        <h1>日历</h1>
        <div class="bar-right">
          <span
            v-if="pendingCount > 0"
            class="pending"
            role="status"
          >{{ pendingCount }} 项待同步…</span>
          <button
            type="button"
            @click="requestPreview"
          >
            AI 调整预览
          </button>
        </div>
      </header>
      <p
        v-if="banner"
        class="banner"
        role="alert"
      >
        {{ banner }}
      </p>
      <p
        v-if="week && week.conflicts.length"
        class="conflicts"
        role="status"
      >
        {{ week.conflicts.length }} 处时间冲突
      </p>
      <FullCalendar :options="options" />
    </main>
    <SchedulePreviewDrawer
      v-if="preview"
      :preview="preview"
      @applied="onApplied"
      @close="preview = null"
    />
  </div>
</template>

<style scoped>
.calendar-layout {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-4);
}
.calendar {
  flex: 1;
  min-width: 0;
}
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.bar-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.pending {
  color: var(--status-ai);
  font-size: 0.85rem;
  font-variant-numeric: tabular-nums;
}
.bar button {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--status-ai);
  color: white;
  cursor: pointer;
}
.banner {
  color: var(--status-urgent);
}
.conflicts {
  color: var(--status-due-soon);
}
/* Tactile drag feedback: lift the event being dragged/resized. */
.calendar-layout :deep(.fc-event.fc-event-dragging),
.calendar-layout :deep(.fc-event.fc-event-resizing),
.calendar-layout :deep(.fc-event-mirror) {
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.28);
  transform: scale(1.02);
  opacity: 0.96;
  z-index: 5;
}
.calendar-layout :deep(.fc-timegrid-event) {
  transition:
    box-shadow 0.15s ease,
    transform 0.12s ease;
  cursor: grab;
}
.calendar-layout.dragging :deep(.fc-timegrid-event) {
  cursor: grabbing;
}
@media (max-width: 720px) {
  .calendar-layout {
    flex-direction: column;
  }
}
@media (prefers-reduced-motion: reduce) {
  .calendar-layout :deep(.fc-timegrid-event) {
    transition: none;
  }
}
</style>
