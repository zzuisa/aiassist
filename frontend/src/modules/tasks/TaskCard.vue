<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Task } from '@/api/tasks'

const props = defineProps<{ task: Task }>()
const emit = defineEmits<{
  (e: 'complete', task: Task): void
  (e: 'open', task: Task): void
  (e: 'add-to-calendar', task: Task): void
}>()

// Status is conveyed by both a colored dot AND a text label (never color alone).
const statusLabel = computed(() => {
  if (props.task.is_fixed) return '固定'
  switch (props.task.status) {
    case 'in_progress':
      return '进行中'
    case 'completed':
      return '已完成'
    case 'cancelled':
      return '已取消'
    default:
      return '待办'
  }
})

const statusClass = computed(() => {
  if (props.task.is_fixed) return 'fixed'
  if (props.task.status === 'completed') return 'done'
  if (props.task.status === 'in_progress') return 'progress'
  return 'todo'
})

// --- Swipe-to-reveal (mobile): drag the card left to expose "添加到日历". ---
const ACTION_W = 120 // px revealed
const THRESHOLD = 48 // px past which the row snaps open
const offset = ref(0) // current translateX (0 .. -ACTION_W)
const dragging = ref(false)
let startX = 0
let startOffset = 0
let moved = false

function onDown(e: PointerEvent): void {
  if (props.task.is_fixed) return
  startX = e.clientX
  startOffset = offset.value
  moved = false
  dragging.value = true
}
function onMove(e: PointerEvent): void {
  if (!dragging.value) return
  const dx = e.clientX - startX
  if (Math.abs(dx) > 4) moved = true
  offset.value = Math.max(-ACTION_W, Math.min(0, startOffset + dx))
}
function onUp(): void {
  if (!dragging.value) return
  dragging.value = false
  offset.value = offset.value < -THRESHOLD ? -ACTION_W : 0
}
function close(): void {
  offset.value = 0
}

// A tap on the body opens the task — unless the row is/just was swiped.
function onBody(): void {
  if (moved || offset.value !== 0) {
    close()
    return
  }
  emit('open', props.task)
}
function onAddCalendar(): void {
  close()
  emit('add-to-calendar', props.task)
}
</script>

<template>
  <div class="swipe-wrap">
    <div
      class="behind"
      aria-hidden="true"
    >
      <button
        class="cal-action tappable"
        type="button"
        :aria-label="`把 ${task.title} 添加到日历`"
        @click="onAddCalendar"
      >
        📅 添加到日历
      </button>
    </div>
    <article
      class="card tappable"
      :class="[statusClass, { dragging }]"
      :style="{ transform: `translateX(${offset}px)` }"
      @pointerdown="onDown"
      @pointermove="onMove"
      @pointerup="onUp"
      @pointercancel="onUp"
    >
      <button
        class="check"
        :aria-label="`完成 ${task.title}`"
        @click="$emit('complete', task)"
      >
        <span aria-hidden="true">{{ task.status === 'completed' ? '✓' : '○' }}</span>
      </button>
      <button
        class="body"
        @click="onBody"
      >
        <span
          class="title"
          :class="{ struck: task.status === 'completed' }"
        >{{ task.title }}</span>
        <span class="meta">
          <span
            class="badge"
            :class="statusClass"
          >{{ statusLabel }}</span>
          <span
            v-if="task.priority > 0"
            class="prio"
          >P{{ task.priority }}</span>
          <span
            v-if="task.start_at"
            class="prio when"
          >📅 已排期</span>
        </span>
      </button>
    </article>
  </div>
</template>

<style scoped>
.swipe-wrap {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-md);
  touch-action: pan-y; /* let vertical scroll through; we own horizontal */
}
.behind {
  position: absolute;
  inset: 0;
  display: flex;
  justify-content: flex-end;
  align-items: stretch;
}
.cal-action {
  border: none;
  width: 120px;
  background: var(--status-ai);
  color: #fff;
  font-size: 0.85rem;
  cursor: pointer;
}
.card {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--status-normal);
  border-radius: var(--radius-md);
  will-change: transform;
  transition:
    transform 0.22s cubic-bezier(0.4, 0, 0.2, 1),
    box-shadow 0.15s ease;
}
.card.dragging {
  transition: box-shadow 0.15s ease; /* follow the finger without lag */
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.14);
}
.card:active {
  transform: scale(0.985);
}
.card.progress {
  border-left-color: var(--status-due-soon);
}
.card.done {
  border-left-color: var(--status-done);
}
.card.fixed {
  border-left-color: var(--status-muted);
}
.check {
  min-width: var(--tap-target);
  min-height: var(--tap-target);
  border: none;
  background: transparent;
  font-size: 1.2rem;
  color: var(--status-done);
  cursor: pointer;
  transition: transform 0.12s ease;
}
.check:active {
  transform: scale(1.25);
}
.body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
  border: none;
  background: transparent;
  color: var(--color-text);
  cursor: pointer;
  min-width: 0;
}
.title.struck {
  text-decoration: line-through;
  color: var(--color-text-muted);
}
.meta {
  display: flex;
  gap: var(--space-2);
  font-size: 0.75rem;
}
.badge {
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--color-surface-2);
  color: var(--color-text-muted);
}
.when {
  color: var(--status-ai);
}
@media (prefers-reduced-motion: reduce) {
  .card {
    transition: none;
  }
}
</style>
