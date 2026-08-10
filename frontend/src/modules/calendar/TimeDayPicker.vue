<script setup lang="ts">
import { computed, ref } from 'vue'
import WheelPicker from '@/modules/calendar/WheelPicker.vue'

// Mobile-first day + time picker. No typing: three momentum wheels for day,
// hour and minute, with a center highlight band. Presented as a bottom sheet.
const props = defineProps<{ title: string; initial?: string | null }>()
const emit = defineEmits<{ (e: 'confirm', iso: string): void; (e: 'cancel'): void }>()

function midnight(d: Date): Date {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return x
}

const now = new Date()
const base = midnight(now)
const start = props.initial ? new Date(props.initial) : new Date(now.getTime() + 3600_000)

// Day column: yesterday .. +60 days, as offsets from today.
const dayItems = computed(() =>
  Array.from({ length: 62 }, (_, k) => {
    const off = k - 1
    const d = new Date(base.getTime() + off * 86400_000)
    let label: string
    if (off === 0) label = '今天'
    else if (off === 1) label = '明天'
    else if (off === -1) label = '昨天'
    else label = `${d.getMonth() + 1}月${d.getDate()}日 周${'日一二三四五六'[d.getDay()]}`
    return { value: off, label }
  }),
)
const hourItems = Array.from({ length: 24 }, (_, h) => ({
  value: h,
  label: String(h).padStart(2, '0'),
}))
const minItems = Array.from({ length: 12 }, (_, m) => ({
  value: m * 5,
  label: String(m * 5).padStart(2, '0'),
}))

const dayOff = ref(Math.round((midnight(start).getTime() - base.getTime()) / 86400_000))
const hour = ref(start.getHours())
const minute = ref(Math.round(start.getMinutes() / 5) * 5 % 60)

const preview = computed(() => {
  const d = new Date(base.getTime() + dayOff.value * 86400_000)
  d.setHours(hour.value, minute.value, 0, 0)
  return d
})
const previewLabel = computed(() => {
  const d = preview.value
  const day = dayItems.value.find((x) => x.value === dayOff.value)?.label ?? ''
  return `${day} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
})

function confirm(): void {
  emit('confirm', preview.value.toISOString())
}
</script>

<template>
  <div
    class="sheet-backdrop"
    @click.self="emit('cancel')"
  >
    <div
      class="sheet"
      role="dialog"
      aria-label="调整时间"
    >
      <header>
        <button
          class="link"
          @click="emit('cancel')"
        >
          取消
        </button>
        <div class="ttl">
          <strong>{{ title }}</strong>
          <span class="pv">{{ previewLabel }}</span>
        </div>
        <button
          class="link done"
          @click="confirm"
        >
          确定
        </button>
      </header>

      <div class="wheels">
        <div
          class="band"
          aria-hidden="true"
        />
        <WheelPicker
          v-model="dayOff"
          :items="dayItems"
          label="日期"
        />
        <WheelPicker
          v-model="hour"
          :items="hourItems"
          label="小时"
        />
        <span class="colon">:</span>
        <WheelPicker
          v-model="minute"
          :items="minItems"
          label="分钟"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.sheet-backdrop {
  position: fixed;
  inset: 0;
  z-index: 55;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  animation: fade 0.2s ease;
}
.sheet {
  width: min(480px, 100%);
  background: var(--color-surface);
  border-radius: var(--radius-lg, 18px) var(--radius-lg, 18px) 0 0;
  padding: var(--space-3) var(--space-4) calc(var(--safe-bottom, 0px) + var(--space-4));
  box-shadow: 0 -10px 40px rgba(0, 0, 0, 0.28);
  animation: rise 0.28s cubic-bezier(0.22, 1, 0.36, 1);
}
@keyframes fade {
  from {
    opacity: 0;
  }
}
@keyframes rise {
  from {
    transform: translateY(100%);
  }
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}
.ttl {
  text-align: center;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.ttl strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pv {
  color: var(--status-normal);
  font-weight: 600;
  font-size: 0.9rem;
  font-variant-numeric: tabular-nums;
}
.link {
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  font-size: 1rem;
  min-height: var(--tap-target);
  padding: 0 var(--space-2);
  cursor: pointer;
}
.link.done {
  color: var(--status-normal);
  font-weight: 700;
}
.wheels {
  position: relative;
  display: flex;
  align-items: stretch;
  gap: var(--space-1);
}
/* Center highlight band the wheels snap into (HCD: shows the active choice). */
.band {
  position: absolute;
  left: 0;
  right: 0;
  top: 80px;
  height: 40px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--status-normal) 12%, transparent);
  pointer-events: none;
}
.colon {
  align-self: center;
  font-weight: 700;
  color: var(--color-text);
}
@media (prefers-reduced-motion: reduce) {
  .sheet,
  .sheet-backdrop {
    animation: none;
  }
}
</style>
