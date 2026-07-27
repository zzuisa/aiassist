<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

// A single scrollable wheel column (iOS-style). Uses native scroll + CSS
// scroll-snap for momentum and smoothness — no per-frame JS, so it stays fluid
// on mobile. The item centered in the highlight band is the selected value.
interface Item {
  value: number
  label: string
}
const props = defineProps<{ items: Item[]; modelValue: number; label?: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: number): void }>()

const ITEM_H = 40
const scroller = ref<HTMLElement | null>(null)
let settleTimer: ReturnType<typeof setTimeout> | null = null

function indexOfValue(v: number): number {
  const i = props.items.findIndex((it) => it.value === v)
  return i < 0 ? 0 : i
}

function scrollToIndex(i: number, smooth = false): void {
  scroller.value?.scrollTo({ top: i * ITEM_H, behavior: smooth ? 'smooth' : 'auto' })
}

function onScroll(): void {
  if (settleTimer) clearTimeout(settleTimer)
  // Debounce until scrolling settles, then read the centered item.
  settleTimer = setTimeout(() => {
    const el = scroller.value
    if (!el) return
    const i = Math.max(0, Math.min(props.items.length - 1, Math.round(el.scrollTop / ITEM_H)))
    const v = props.items[i].value
    if (v !== props.modelValue) emit('update:modelValue', v)
  }, 90)
}

onMounted(() => scrollToIndex(indexOfValue(props.modelValue)))
// Reflect external changes (e.g., day change reclamping the value) without a loop.
watch(
  () => props.modelValue,
  (v) => {
    const el = scroller.value
    if (!el) return
    const target = indexOfValue(v) * ITEM_H
    if (Math.abs(el.scrollTop - target) > 2) scrollToIndex(indexOfValue(v), true)
  },
)
</script>

<template>
  <div class="col">
    <div
      ref="scroller"
      class="wheel"
      role="listbox"
      :aria-label="label"
      @scroll="onScroll"
    >
      <div class="pad" />
      <button
        v-for="it in items"
        :key="it.value"
        type="button"
        class="item"
        :class="{ sel: it.value === modelValue }"
        @click="emit('update:modelValue', it.value)"
      >
        {{ it.label }}
      </button>
      <div class="pad" />
    </div>
  </div>
</template>

<style scoped>
.col {
  position: relative;
  flex: 1;
  min-width: 0;
}
.wheel {
  height: 200px; /* 5 rows of 40px */
  overflow-y: auto;
  scroll-snap-type: y mandatory;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  /* Fade top/bottom so the center reads as the focus (HCD: clear affordance). */
  -webkit-mask-image: linear-gradient(
    to bottom,
    transparent,
    #000 34%,
    #000 66%,
    transparent
  );
  mask-image: linear-gradient(to bottom, transparent, #000 34%, #000 66%, transparent);
}
.wheel::-webkit-scrollbar {
  display: none;
}
.pad {
  height: 80px; /* 2 rows so first/last item can center */
}
.item {
  height: 40px;
  width: 100%;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  font-size: 1rem;
  scroll-snap-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition:
    color 0.15s ease,
    transform 0.15s ease;
  font-variant-numeric: tabular-nums;
}
.item.sel {
  color: var(--color-text);
  font-weight: 700;
  transform: scale(1.08);
}
@media (prefers-reduced-motion: reduce) {
  .item {
    transition: none;
  }
  .wheel {
    scroll-behavior: auto;
  }
}
</style>
