<script setup lang="ts">
import { computed } from 'vue'
import type { HabitStats } from '@/api/habits'

const props = defineProps<{ stats: HabitStats }>()

// Last 12 weeks, one column per week, colored by daily completion count.
const cells = computed(() => {
  const days: Array<{ date: string; level: number }> = []
  const today = new Date()
  for (let i = 83; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(today.getDate() - i)
    const key = d.toISOString().slice(0, 10)
    const bucket = props.stats.heatmap[key]
    const completed = bucket?.completed ?? 0
    days.push({ date: key, level: Math.min(completed, 4) })
  }
  return days
})
</script>

<template>
  <div
    class="heatmap"
    role="img"
    aria-label="习惯完成热力图"
  >
    <div class="grid">
      <span
        v-for="c in cells"
        :key="c.date"
        class="cell"
        :data-level="c.level"
        :title="`${c.date}: ${c.level} 次完成`"
      />
    </div>
    <p class="legend">
      连续 {{ stats.streak }} 天 · 完成率 {{ Math.round(stats.completion_rate * 100) }}%
    </p>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-rows: repeat(7, 1fr);
  grid-auto-flow: column;
  gap: 3px;
}
.cell {
  width: 12px;
  height: 12px;
  border-radius: 2px;
  background: var(--color-surface-2);
}
.cell[data-level='1'] {
  background: color-mix(in srgb, var(--status-done) 35%, transparent);
}
.cell[data-level='2'] {
  background: color-mix(in srgb, var(--status-done) 55%, transparent);
}
.cell[data-level='3'] {
  background: color-mix(in srgb, var(--status-done) 75%, transparent);
}
.cell[data-level='4'] {
  background: var(--status-done);
}
.legend {
  margin-top: var(--space-2);
  color: var(--color-text-muted);
  font-size: 0.8rem;
}
</style>
