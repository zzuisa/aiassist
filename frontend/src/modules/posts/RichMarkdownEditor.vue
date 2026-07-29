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
</script>

<template>
  <div class="rich-wrap">
    <div
      v-show="!failed"
      ref="root"
      class="rich-root"
    />
    <textarea
      v-if="failed"
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
