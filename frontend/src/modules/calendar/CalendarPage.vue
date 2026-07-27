<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import FullCalendar from '@fullcalendar/vue3'
import timeGridPlugin from '@fullcalendar/timegrid'
import listPlugin from '@fullcalendar/list'
import interactionPlugin from '@fullcalendar/interaction'
import type { CalendarOptions, EventClickArg, EventDropArg } from '@fullcalendar/core'
import type { EventResizeDoneArg } from '@fullcalendar/interaction'
import { calendarApi, type SchedulePreview, type Task, type WeekCalendar } from '@/api/calendar'
import { persistReschedule } from '@/modules/calendar/useReschedule'
import { computeSlotRange } from '@/modules/calendar/slotRange'
import { useTasksStore } from '@/stores/tasks'
import SchedulePreviewDrawer from '@/modules/calendar/SchedulePreviewDrawer.vue'
import CalendarEventPopover from '@/modules/calendar/CalendarEventPopover.vue'
import CalendarEventNoteEditor from '@/modules/calendar/CalendarEventNoteEditor.vue'
import TimeDayPicker from '@/modules/calendar/TimeDayPicker.vue'

const tasks = useTasksStore()
const week = ref<WeekCalendar | null>(null)
const preview = ref<SchedulePreview | null>(null)
const banner = ref('')
const dragging = ref(false)
const pop = ref<{ task: Task; x: number; y: number } | null>(null)
const popBusy = ref(false)
const editorTask = ref<Task | null>(null)

function openNote(): void {
  if (pop.value) {
    editorTask.value = pop.value.task
    closePop()
  }
}

const pickerTask = ref<Task | null>(null)
function openPicker(): void {
  if (pop.value) {
    pickerTask.value = pop.value.task
    closePop()
  }
}
async function onPickTime(iso: string): Promise<void> {
  const t = pickerTask.value
  pickerTask.value = null
  if (!t) return
  // Preserve the event's existing duration; default to 30 minutes.
  const durMs =
    t.due_at && t.start_at
      ? new Date(t.due_at).getTime() - new Date(t.start_at).getTime()
      : 30 * 60_000
  const start = new Date(iso)
  const outcome = await persistReschedule(
    t,
    start.toISOString(),
    new Date(start.getTime() + durMs).toISOString(),
  )
  if (outcome.ok) {
    banner.value = ''
    await load()
    tasks.markChanged()
  } else {
    banner.value = outcome.reason === 'fixed_event' ? '固定事件不能被移动。' : '保存失败，请重试。'
  }
}
// Drives the elapsed-time shading; refreshed every minute so the past/future
// boundary follows the clock (FR-015).
const nowTick = ref(Date.now())
let nowTimer: ReturnType<typeof setInterval> | null = null

function onEventClick(arg: EventClickArg): void {
  const task = arg.event.extendedProps.task as Task | undefined
  if (!task) return
  const rect = (arg.el as HTMLElement).getBoundingClientRect()
  // Keep the popover inside the viewport on both desktop and mobile.
  const x = rect.right + 268 > window.innerWidth ? Math.max(8, rect.left - 268) : rect.right + 8
  const y = Math.min(rect.top, window.innerHeight - 220)
  pop.value = { task, x, y }
}
function closePop(): void {
  pop.value = null
}

async function afterPopMutation(): Promise<void> {
  await load()
  tasks.markChanged()
  if (pop.value) {
    const fresh = (week.value?.events ?? []).find((e) => e.id === pop.value!.task.id)
    if (fresh) pop.value = { ...pop.value, task: fresh }
    else closePop()
  }
}

async function toggleComplete(): Promise<void> {
  if (!pop.value) return
  const t = pop.value.task
  popBusy.value = true
  try {
    if (t.status === 'completed') await tasks.patch(t.id, { version: t.version, status: 'todo' })
    else await tasks.complete(t)
    await afterPopMutation()
  } catch {
    banner.value = '保存失败，请重试。'
  } finally {
    popBusy.value = false
  }
}

async function toggleImportant(): Promise<void> {
  if (!pop.value) return
  const t = pop.value.task
  popBusy.value = true
  try {
    await tasks.patch(t.id, { version: t.version, importance: t.importance > 0 ? 0 : 4 })
    await afterPopMutation()
  } catch {
    banner.value = '保存失败，请重试。'
  } finally {
    popBusy.value = false
  }
}

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

onMounted(() => {
  void load()
  nowTimer = setInterval(() => (nowTick.value = Date.now()), 60_000)
})

const calendarEvents = computed(() => {
  const items = (week.value?.events ?? []).map((t) => ({
    id: t.id,
    title: t.title,
    start: t.start_at ?? undefined,
    end: t.due_at ?? undefined,
    editable: !t.is_fixed, // fixed events are not draggable/resizable
    color: t.is_fixed ? 'var(--status-muted)' : 'var(--status-normal)',
    extendedProps: { task: t },
  })) as Record<string, unknown>[]
  // Grey the elapsed region: a background span from the week start to now. It
  // sits behind real events, so event text and important backgrounds stay clear.
  const weekStart = new Date(startsOn.value)
  const weekEnd = new Date(weekStart.getTime() + 7 * 864e5)
  const now = new Date(nowTick.value)
  if (now > weekStart) {
    items.push({
      start: weekStart.toISOString(),
      end: (now < weekEnd ? now : weekEnd).toISOString(),
      display: 'background',
      color: 'var(--status-elapsed-bg)',
      editable: false,
    })
  }
  return items
})

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
  if (nowTimer) clearInterval(nowTimer)
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
  eventClick: onEventClick,
  eventClassNames: (arg) => {
    const t = arg.event.extendedProps.task as Task | undefined
    const c: string[] = []
    if (!t) return c
    if (t.importance > 0) c.push('evt-important')
    if (t.status === 'completed') c.push('evt-done')
    return c
  },
  eventContent: (arg) => {
    // Name first, time below (FR-017); a completed event shows an emoji.
    const t = arg.event.extendedProps.task as Task | undefined
    if (!t) return undefined // background (elapsed) span: default rendering
    const wrap = document.createElement('div')
    wrap.className = 'evt'
    const title = document.createElement('div')
    title.className = 'evt-title'
    title.textContent = (t.status === 'completed' ? '\u2705 ' : '') + t.title
    const time = document.createElement('div')
    time.className = 'evt-time'
    time.textContent = arg.timeText
    wrap.appendChild(title)
    wrap.appendChild(time)
    return { domNodes: [wrap] }
  },
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
    <div
      v-if="pop"
      class="pop-backdrop"
      @click="closePop"
    >
      <CalendarEventPopover
        :task="pop.task"
        :busy="popBusy"
        :style="{ left: pop.x + 'px', top: pop.y + 'px' }"
        @toggle-complete="toggleComplete"
        @toggle-important="toggleImportant"
        @adjust-time="openPicker"
        @add-note="openNote"
        @close="closePop"
      />
    </div>
    <div
      v-if="editorTask"
      class="note-overlay"
      @click="editorTask = null"
    >
      <CalendarEventNoteEditor
        :task-id="editorTask.id"
        :title="editorTask.title"
        @saved="tasks.markChanged()"
        @close="editorTask = null"
      />
    </div>
    <TimeDayPicker
      v-if="pickerTask"
      :title="pickerTask.title"
      :initial="pickerTask.start_at"
      @confirm="onPickTime"
      @cancel="pickerTask = null"
    />
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
/* Event card: name first, time below (FR-017). */
.calendar-layout :deep(.evt-title) {
  font-weight: 600;
  line-height: 1.15;
  overflow: hidden;
  text-overflow: ellipsis;
}
.calendar-layout :deep(.evt-time) {
  font-size: 0.72rem;
  opacity: 0.85;
}
/* Important: soft red background with readable text; never color-only. */
.calendar-layout :deep(.evt-important) {
  background: var(--status-important-bg) !important;
  border-color: var(--status-urgent) !important;
  color: var(--status-important-text) !important;
}
.calendar-layout :deep(.evt-done) {
  opacity: 0.9;
}
.pop-backdrop {
  position: fixed;
  inset: 0;
  z-index: 35;
}
.note-overlay {
  position: fixed;
  inset: 0;
  z-index: 45;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.4);
  padding: var(--space-4);
}

/* ---- Deep polish: modern, GPU-friendly, restrained (transform/opacity only) ---- */
.calendar {
  animation: cal-in 0.32s cubic-bezier(0.22, 1, 0.36, 1);
}
@keyframes cal-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
}
.calendar-layout :deep(.fc-timegrid-event) {
  border-radius: 8px;
  border: none;
  transition:
    transform 0.12s ease,
    box-shadow 0.16s ease,
    filter 0.16s ease;
}
.calendar-layout :deep(.fc-timegrid-event:active) {
  transform: scale(0.98);
}
@media (hover: hover) {
  .calendar-layout :deep(.fc-timegrid-event:hover) {
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18);
    filter: brightness(1.03);
    z-index: 3;
  }
}
/* A gently pulsing "now" line so the current moment is always locatable (HCD). */
.calendar-layout :deep(.fc-timegrid-now-indicator-line) {
  border-color: var(--status-urgent);
  animation: now-pulse 2.6s ease-in-out infinite;
}
@keyframes now-pulse {
  50% {
    box-shadow: 0 0 9px rgba(220, 38, 38, 0.45);
  }
}

/* Mobile: the title is the priority — let it wrap to two lines and stay readable;
   drop the time on very short events instead of cramming both. */
@media (max-width: 720px) {
  .calendar-layout :deep(.evt-title) {
    font-size: 0.82rem;
    line-height: 1.2;
    white-space: normal;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .calendar-layout :deep(.evt-time) {
    font-size: 0.64rem;
  }
  .calendar-layout :deep(.fc-timegrid-event-short .evt-time) {
    display: none;
  }
  .calendar-layout :deep(.fc-timegrid-event-short .evt-title) {
    -webkit-line-clamp: 1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .calendar,
  .calendar-layout :deep(.fc-timegrid-now-indicator-line) {
    animation: none;
  }
}
</style>
