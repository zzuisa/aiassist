<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import FullCalendar from '@fullcalendar/vue3'
import timeGridPlugin from '@fullcalendar/timegrid'
import listPlugin from '@fullcalendar/list'
import interactionPlugin from '@fullcalendar/interaction'
import type { CalendarOptions, EventDropArg } from '@fullcalendar/core'
import type { EventResizeDoneArg } from '@fullcalendar/interaction'
import { calendarApi, type SchedulePreview, type Task, type WeekCalendar } from '@/api/calendar'
import { persistReschedule } from '@/modules/calendar/useReschedule'
import { computeSlotRange } from '@/modules/calendar/slotRange'
import SchedulePreviewDrawer from '@/modules/calendar/SchedulePreviewDrawer.vue'

const week = ref<WeekCalendar | null>(null)
const preview = ref<SchedulePreview | null>(null)
const banner = ref('')

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

async function onChange(arg: EventDropArg | EventResizeDoneArg): Promise<void> {
  const task = arg.event.extendedProps.task as Task
  const outcome = await persistReschedule(
    task,
    arg.event.start?.toISOString() ?? null,
    arg.event.end?.toISOString() ?? null,
  )
  if (!outcome.ok) {
    arg.revert() // never leave a stale/failed position on screen
    banner.value =
      outcome.reason === 'version_conflict'
        ? '该任务已被其他修改更新，请刷新后重试。'
        : outcome.reason === 'fixed_event'
          ? '固定事件不能被移动。'
          : '保存失败，已恢复原位置。'
  } else {
    banner.value = ''
    await load()
  }
}

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
}))
</script>

<template>
  <div class="calendar-layout">
    <main class="calendar">
      <header class="bar">
        <h1>日历</h1>
        <button
          type="button"
          @click="requestPreview"
        >
          AI 调整预览
        </button>
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
@media (max-width: 720px) {
  .calendar-layout {
    flex-direction: column;
  }
}
</style>
