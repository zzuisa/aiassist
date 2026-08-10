<script setup lang="ts">
// Milkdown (Crepe) rich editor (spec 005, US2, T056).
//
// WYSIWYG editing over the SAME canonical Markdown. The supported-block matrix
// for the MVP is what Crepe renders by default: headings, bold/italic/strike,
// lists, quote, code block, link, image, table, hr. On every edit it emits the
// serialized Markdown so the shell can autosave the one source of truth. If the
// editor fails to initialise it degrades to a plain textarea (never blocks
// writing).
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { Crepe } from '@milkdown/crepe'
import '@milkdown/crepe/theme/common/style.css'
import '@milkdown/crepe/theme/frame.css'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const root = ref<HTMLDivElement | null>(null)
const wrap = ref<HTMLDivElement | null>(null)
const fallback = ref<HTMLTextAreaElement | null>(null)
const failed = ref(false)
const crepe = shallowRef<Crepe | null>(null)

onMounted(async () => {
  if (!root.value) return
  try {
    const instance = new Crepe({ root: root.value, defaultValue: props.modelValue })
    instance.on((listener) => {
      listener.markdownUpdated((_ctx, markdown) => {
        if (markdown !== props.modelValue) emit('update:modelValue', markdown)
      })
    })
    await instance.create()
    crepe.value = instance
  } catch {
    failed.value = true
  }
})

onBeforeUnmount(() => {
  try {
    crepe.value?.destroy()
  } catch {
    /* already torn down */
  }
})

function onFallbackInput(e: Event): void {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
}

function scrollToHeading(index: number, line = 1, offset = 0): void {
  if (failed.value && fallback.value) {
    const el = fallback.value
    el.focus({ preventScroll: true })
    el.setSelectionRange(offset, offset)
    const lineHeight = Number.parseFloat(window.getComputedStyle(el).lineHeight) || 25.5
    el.scrollTo({ top: Math.max(0, (line - 1) * lineHeight - 16), behavior: 'smooth' })
    return
  }
  const container = wrap.value
  const target = root.value?.querySelector<HTMLElement>(`h1, h2, h3, h4, h5, h6`)
  const headings = root.value?.querySelectorAll<HTMLElement>('h1, h2, h3, h4, h5, h6')
  const heading = headings?.item(index) ?? target
  if (!container || !heading) return
  const top = heading.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop
  container.scrollTo({ top: Math.max(0, top - 16), behavior: 'smooth' })
  heading.classList.add('outline-target')
  window.setTimeout(() => heading.classList.remove('outline-target'), 1400)
}

defineExpose({ scrollToHeading })
</script>

<template>
  <div
    ref="wrap"
    class="rich-wrap"
  >
    <div
      v-show="!failed"
      ref="root"
      class="rich-root"
    />
    <textarea
      v-if="failed"
      ref="fallback"
      class="rich-fallback"
      :value="modelValue"
      @input="onFallbackInput"
    />
  </div>
</template>

<style scoped>
.rich-wrap {
  height: 100%;
  overflow-y: auto;
}
.rich-root {
  min-height: 320px;
}
.rich-root :deep(.outline-target) {
  border-radius: var(--radius-sm);
  background: var(--color-accent-soft, #eef2ff);
  transition: background 0.25s ease;
}
.rich-fallback {
  width: 100%;
  height: 100%;
  min-height: 320px;
  border: none;
  outline: none;
  padding: var(--space-4);
  font-family: var(--font-mono, ui-monospace, monospace);
  resize: none;
}
</style>
