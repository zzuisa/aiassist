<script setup lang="ts">
// Canonical source-mode editor (spec 005, US2, T055).
// A plain Markdown textarea that is the single source of truth. It retains the
// caret across external value updates (e.g. autosave reconciliation) and exposes
// a Tab-to-indent affordance so code/lists are comfortable to write.
import { nextTick, ref, watch } from 'vue'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const area = ref<HTMLTextAreaElement | null>(null)

function scrollToPosition(line: number, offset: number): void {
  const el = area.value
  if (!el) return
  el.focus({ preventScroll: true })
  const caret = Math.max(0, Math.min(offset, el.value.length))
  el.setSelectionRange(caret, caret)
  const styles = window.getComputedStyle(el)
  const lineHeight = Number.parseFloat(styles.lineHeight) || 25.5
  const paddingTop = Number.parseFloat(styles.paddingTop) || 0
  el.scrollTo({ top: Math.max(0, (line - 1) * lineHeight + paddingTop - 16), behavior: 'smooth' })
}

defineExpose({ scrollToPosition })

// Keep the caret stable when the bound value is replaced from outside while the
// element is focused (the parent may reconcile after a save).
watch(
  () => props.modelValue,
  async (val) => {
    const el = area.value
    if (!el || document.activeElement !== el || el.value === val) return
    const pos = el.selectionStart
    await nextTick()
    el.selectionStart = el.selectionEnd = Math.min(pos, val.length)
  },
)

function onInput(e: Event): void {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key !== 'Tab') return
  e.preventDefault()
  const el = e.target as HTMLTextAreaElement
  const start = el.selectionStart
  const end = el.selectionEnd
  const next = props.modelValue.slice(0, start) + '  ' + props.modelValue.slice(end)
  emit('update:modelValue', next)
  void nextTick(() => {
    el.selectionStart = el.selectionEnd = start + 2
  })
}
</script>

<template>
  <textarea
    ref="area"
    class="md-source"
    spellcheck="false"
    :value="modelValue"
    @input="onInput"
    @keydown="onKeydown"
  />
</template>

<style scoped>
.md-source {
  width: 100%;
  height: 100%;
  min-height: 320px;
  resize: none;
  border: none;
  outline: none;
  padding: var(--space-4);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.95rem;
  line-height: 1.7;
  background: var(--color-surface, #fff);
  color: var(--color-text, #111827);
  tab-size: 2;
}
</style>
