<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Habit, HabitLog } from '@/api/habits'

const props = defineProps<{ habit: Habit; log: HabitLog | null }>()
const emit = defineEmits<{
  (e: 'checkin', habitId: string, durationSeconds?: number): void
  (e: 'skip', habitId: string): void
}>()

// One-tap check-in and an optional timer that does not depend on hover.
const timing = ref(false)
const elapsed = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

const done = computed(() => props.log?.status === 'completed')
const skipped = computed(() => props.log?.status === 'skipped')

function toggleTimer(): void {
  if (timing.value) {
    if (timer) clearInterval(timer)
    timer = null
    timing.value = false
    emit('checkin', props.habit.id, elapsed.value)
    elapsed.value = 0
  } else {
    timing.value = true
    elapsed.value = 0
    timer = setInterval(() => {
      elapsed.value += 1
    }, 1000)
  }
}
</script>

<template>
  <article
    class="habit"
    :class="{ done, skipped }"
  >
    <div class="info">
      <span class="name">{{ habit.name }}</span>
      <span class="status">
        <template v-if="done">已完成</template>
        <template v-else-if="skipped">已跳过</template>
        <template v-else>待打卡</template>
      </span>
    </div>
    <div class="actions">
      <button
        class="checkin"
        :disabled="done"
        :aria-label="`打卡 ${habit.name}`"
        @click="emit('checkin', habit.id)"
      >
        ✓
      </button>
      <button
        class="timer"
        :aria-label="`计时 ${habit.name}`"
        @click="toggleTimer"
      >
        {{ timing ? `${elapsed}s ⏹` : '⏱' }}
      </button>
      <button
        class="skip"
        :aria-label="`跳过 ${habit.name}`"
        @click="emit('skip', habit.id)"
      >
        跳过
      </button>
    </div>
  </article>
</template>

<style scoped>
.habit {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--status-normal);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}
.habit.done {
  border-left-color: var(--status-done);
}
.habit.skipped {
  border-left-color: var(--status-muted);
}
.info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.status {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}
.actions {
  display: flex;
  gap: var(--space-2);
}
button {
  min-height: var(--tap-target);
  min-width: var(--tap-target);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
.checkin {
  color: var(--status-done);
}
button:disabled {
  opacity: 0.5;
}
</style>
