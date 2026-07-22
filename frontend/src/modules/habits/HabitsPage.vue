<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { habitsApi, type Habit, type HabitLog, type HabitStats, type SkipReason } from '@/api/habits'
import HabitCard from '@/modules/habits/HabitCard.vue'
import HabitHeatmap from '@/modules/habits/HabitHeatmap.vue'
import SkipSheet from '@/modules/habits/SkipSheet.vue'

const habits = ref<Habit[]>([])
const logs = ref<Record<string, HabitLog>>({})
const stats = ref<HabitStats | null>(null)
const skipping = ref<Habit | null>(null)
const showCreate = ref(false)
const newName = ref('')
const newRule = ref('FREQ=DAILY')

const today = new Date().toISOString().slice(0, 10)

async function refresh(): Promise<void> {
  habits.value = await habitsApi.list()
  const from = new Date()
  from.setDate(from.getDate() - 83)
  stats.value = await habitsApi.stats(from.toISOString().slice(0, 10), today)
}

onMounted(refresh)

async function onCheckin(habitId: string, durationSeconds?: number): Promise<void> {
  const log = await habitsApi.checkIn(habitId, today, 'completed', durationSeconds)
  logs.value = { ...logs.value, [habitId]: log }
  await refresh()
}

async function onSkipConfirm(reason: SkipReason, note: string): Promise<void> {
  if (!skipping.value) return
  const log = await habitsApi.skip(skipping.value.id, today, reason, note)
  logs.value = { ...logs.value, [skipping.value.id]: log }
  skipping.value = null
}

async function createHabit(): Promise<void> {
  if (!newName.value.trim()) return
  await habitsApi.create({ name: newName.value.trim(), recurrence_rule: newRule.value })
  newName.value = ''
  showCreate.value = false
  await refresh()
}
</script>

<template>
  <main class="habits">
    <header class="head">
      <h1>习惯</h1>
      <button
        type="button"
        @click="showCreate = !showCreate"
      >
        新建习惯
      </button>
    </header>

    <form
      v-if="showCreate"
      class="create"
      @submit.prevent="createHabit"
    >
      <input
        v-model="newName"
        placeholder="习惯名称"
        aria-label="习惯名称"
      >
      <select
        v-model="newRule"
        aria-label="重复规则"
      >
        <option value="FREQ=DAILY">
          每天
        </option>
        <option value="FREQ=WEEKLY;BYDAY=MO,WE,FR">
          周一三五
        </option>
        <option value="FREQ=WEEKLY;BYDAY=SA,SU">
          周末
        </option>
      </select>
      <button type="submit">
        创建
      </button>
    </form>

    <HabitHeatmap
      v-if="stats"
      :stats="stats"
    />

    <section aria-label="今日习惯">
      <p
        v-if="habits.length === 0"
        class="muted"
      >
        还没有习惯，创建一个开始吧。
      </p>
      <div class="list">
        <HabitCard
          v-for="h in habits"
          :key="h.id"
          :habit="h"
          :log="logs[h.id] ?? null"
          @checkin="onCheckin"
          @skip="() => (skipping = h)"
        />
      </div>
    </section>

    <div
      v-if="skipping"
      class="overlay"
    >
      <SkipSheet
        :habit-name="skipping.name"
        @confirm="onSkipConfirm"
        @cancel="skipping = null"
      />
    </div>
  </main>
</template>

<style scoped>
.habits {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 720px;
  margin: 0 auto;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.head button {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--status-normal);
  color: white;
  cursor: pointer;
}
.create {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.create input,
.create select {
  min-height: var(--tap-target);
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
}
.list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.muted {
  color: var(--color-text-muted);
}
.overlay {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: end center;
  background: rgba(0, 0, 0, 0.3);
  padding: var(--space-4);
}
</style>
