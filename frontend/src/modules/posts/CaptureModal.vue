<script setup lang="ts">
// Minimal accessible modal shell shared by the capture dialogs (US1).
// Renders an overlay + centered card; emits `close` on backdrop click or Esc.
import { onBeforeUnmount, onMounted } from 'vue'

defineProps<{ title: string; busy?: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <div
    class="capture-overlay"
    @click.self="emit('close')"
  >
    <div
      class="capture-card"
      role="dialog"
      aria-modal="true"
    >
      <header class="capture-card__head">
        <h2>{{ title }}</h2>
        <button
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
