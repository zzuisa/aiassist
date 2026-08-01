<script setup lang="ts">
// Minimal accessible modal shell shared by the capture dialogs (US1).
// Renders an overlay + centered card; emits `close` on backdrop click or Esc.
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps<{ title: string; busy?: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()
const dialog = ref<HTMLElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
const titleId = `capture-dialog-${Math.random().toString(36).slice(2)}`
let previousFocus: HTMLElement | null = null

function focusableElements(): HTMLElement[] {
  if (!dialog.value) return []
  return [...dialog.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
  )]
}

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') emit('close')
  if (e.key !== 'Tab') return
  const items = focusableElements()
  if (!items.length) return
  const first = items[0]
  const last = items.at(-1)!
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault()
    first.focus()
  }
}
onMounted(() => {
  previousFocus = document.activeElement as HTMLElement | null
  document.addEventListener('keydown', onKey)
  closeButton.value?.focus()
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  previousFocus?.focus()
})
</script>

<template>
  <div
    class="capture-overlay"
    @click.self="emit('close')"
  >
    <div
      ref="dialog"
      class="capture-card"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
    >
      <header class="capture-card__head">
        <h2 :id="titleId">
          {{ title }}
        </h2>
        <button
          ref="closeButton"
          type="button"
          class="capture-card__close"
          :disabled="busy"
          aria-label="关闭"
          @click="emit('close')"
        >
          ×
        </button>
      </header>
      <div class="capture-card__body">
        <slot />
      </div>
      <footer class="capture-card__foot">
        <slot name="footer" />
      </footer>
    </div>
  </div>
</template>

<style scoped>
.capture-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  z-index: 50;
}
.capture-card {
  background: var(--color-surface, #fff);
  border-radius: var(--radius-md, 0.75rem);
  width: 100%;
  max-width: 560px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.capture-card__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border);
}
.capture-card__head h2 {
  margin: 0;
  font-size: 1.05rem;
}
.capture-card__close {
  border: none;
  background: none;
  font-size: 1.5rem;
  line-height: 1;
  cursor: pointer;
  color: var(--color-text-muted);
}
.capture-card__body {
  padding: var(--space-4);
  overflow-y: auto;
}
.capture-card__foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--color-border);
}
</style>
